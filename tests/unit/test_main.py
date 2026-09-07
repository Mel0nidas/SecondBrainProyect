"""Tests del webhook de Telegram (app/main.py).

Se mockean: el modelo del Router (siempre corre primero, hasta para
comandos) y ``enviar_mensaje`` (no se manda nada real a Telegram). El
checkpointer usa un archivo SQLite temporal, no el del proyecto real.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import (
    _armar_briefing,
    _disparar_recordatorios_vencidos,
    _enviar_briefing_si_toca,
    _enviar_digest_si_toca,
    _proxima_ocurrencia,
    _sumar_meses,
    app,
)
from grafo.estado import Intencion, NotaImagenPropuesta, NotaPropuesta, SalidaRouter
from mcp_obsidian import operaciones
from recordatorios import almacen

CHAT_ID_AUTORIZADO = 999
SECRET = "el-secreto-de-prueba"


@pytest.fixture(autouse=True)
def _entorno_de_prueba(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_CHECKPOINTS_SQLITE", str(tmp_path / "checkpoints.sqlite"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-de-prueba")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_CHAT_ID_AUTORIZADO", str(CHAT_ID_AUTORIZADO))


@pytest.fixture
def cliente() -> Iterator[TestClient]:
    with TestClient(app) as cliente_de_prueba:
        yield cliente_de_prueba


def _actualizacion(chat_id: int, texto: str) -> dict[str, object]:
    return {"message": {"chat": {"id": chat_id}, "text": texto}}


def _headers(secret: str | None = SECRET) -> dict[str, str]:
    return {"X-Telegram-Bot-Api-Secret-Token": secret} if secret else {}


def test_mensaje_de_chat_no_autorizado_se_ignora(cliente: TestClient) -> None:
    with patch("app.main.enviar_mensaje") as enviar_mock:
        respuesta = cliente.post(
            "/webhook/telegram", json=_actualizacion(111, "hola"), headers=_headers()
        )

    assert respuesta.status_code == 200
    enviar_mock.assert_not_called()


def test_mensaje_sin_secret_correcto_se_ignora(cliente: TestClient) -> None:
    with patch("app.main.enviar_mensaje") as enviar_mock:
        respuesta = cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "hola"),
            headers=_headers(secret="secreto-incorrecto"),
        )

    assert respuesta.status_code == 200
    enviar_mock.assert_not_called()


def test_comando_ayuda_responde_por_telegram(cliente: TestClient) -> None:
    salida_comando = SalidaRouter(clase=Intencion.COMANDO, confianza=0.99)

    with (
        patch("grafo.nodos.router.ChatAnthropic") as modelo_mock,
        patch("app.main.enviar_mensaje") as enviar_mock,
    ):
        modelo_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            salida_comando
        )

        respuesta = cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/ayuda"),
            headers=_headers(),
        )

    assert respuesta.status_code == 200
    enviar_mock.assert_called_once()
    chat_id_enviado, texto_enviado = enviar_mock.call_args[0]
    assert chat_id_enviado == CHAT_ID_AUTORIZADO
    assert "Comandos disponibles" in texto_enviado


def test_probar_confirmacion_pausa_y_despues_resume(cliente: TestClient) -> None:
    salida_comando = SalidaRouter(clase=Intencion.COMANDO, confianza=0.99)

    with (
        patch("grafo.nodos.router.ChatAnthropic") as modelo_mock,
        patch("app.main.enviar_mensaje") as enviar_mock,
    ):
        modelo_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            salida_comando
        )

        primera = cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/probar_confirmacion"),
            headers=_headers(),
        )
        segunda = cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "si"),
            headers=_headers(),
        )

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert enviar_mock.call_count == 2

    _, texto_pregunta = enviar_mock.call_args_list[0][0]
    assert "Confirmas" in texto_pregunta

    _, texto_final = enviar_mock.call_args_list[1][0]
    assert "CONFIRMADA" in texto_final


def test_foto_se_baja_y_llega_al_grafo_como_ruta(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una foto se guarda en la boveda y al grafo le llega su RUTA, no los bytes.

    Es la pieza clave de la Fase 7: el estado del grafo se serializa al
    checkpointer en cada paso, asi que meterle imagenes enteras lo haria
    crecer sin control.
    """
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path / "boveda"))

    actualizacion = {
        "message": {
            "chat": {"id": CHAT_ID_AUTORIZADO},
            "caption": "pizarra de la reunion",
            # Telegram manda varios tamaños; se usa el ultimo (el mayor).
            "photo": [
                {"file_id": "chico", "width": 90},
                {"file_id": "grande", "width": 1280},
            ],
        }
    }

    # Se parchean las dependencias INTERNAS del archivista, no el nodo
    # entero: el grafo ya quedo compilado con una referencia directa a
    # la funcion cuando arranco el server, asi que parchear el nombre
    # del modulo a esta altura no tendria ningun efecto.
    with (
        patch("app.main.descargar_archivo") as descargar_mock,
        patch("app.main.enviar_mensaje"),
        patch("grafo.nodos.archivista.ChatAnthropic") as modelo_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.archivista.indexar_nota"),
    ):
        descargar_mock.return_value = b"bytes-de-la-foto"
        modelo_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            NotaImagenPropuesta(
                titulo="Pizarra",
                tags=["reunion"],
                transcripcion="lo que se lee",
                descripcion="una pizarra",
            )
        )
        llamar_mock.return_value = ["30-imagenes/pizarra.md"]

        respuesta = cliente.post(
            "/webhook/telegram", json=actualizacion, headers=_headers()
        )

    assert respuesta.status_code == 200

    # Se bajo el tamaño MAS GRANDE, no el primero de la lista.
    descargar_mock.assert_called_once_with("grande")

    # Y la foto quedo escrita en la carpeta que manda el diseño (§2.5).
    guardadas = list((tmp_path / "boveda" / "30-imagenes").iterdir())
    assert len(guardadas) == 1
    assert guardadas[0].read_bytes() == b"bytes-de-la-foto"


def test_mensaje_sin_foto_ni_texto_no_rompe(cliente: TestClient) -> None:
    """Un update raro (ej: una reaccion) se ignora sin explotar."""
    with patch("app.main.enviar_mensaje") as enviar_mock:
        respuesta = cliente.post(
            "/webhook/telegram", json={"edited_message": {}}, headers=_headers()
        )

    assert respuesta.status_code == 200
    enviar_mock.assert_not_called()


def test_imagen_enviada_como_documento_se_baja_y_se_guarda(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una imagen 'enviada como archivo' llega en "document", no en "photo".

    Antes se ignoraba en silencio; ahora se procesa igual que una foto
    comprimida, respetando la extension real (acá .png).
    """
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path / "boveda"))

    actualizacion = {
        "message": {
            "chat": {"id": CHAT_ID_AUTORIZADO},
            "document": {
                "file_id": "doc-1",
                "file_name": "pizarra.png",
                "mime_type": "image/png",
            },
        }
    }

    with (
        patch("app.main.descargar_archivo") as descargar_mock,
        patch("app.main.enviar_mensaje"),
        patch("grafo.nodos.archivista.ChatAnthropic") as modelo_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.archivista.indexar_nota"),
    ):
        descargar_mock.return_value = b"bytes-png"
        modelo_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            NotaImagenPropuesta(
                titulo="Pizarra", tags=["reunion"], transcripcion="", descripcion="una pizarra"
            )
        )
        llamar_mock.return_value = ["30-imagenes/pizarra.md"]

        respuesta = cliente.post("/webhook/telegram", json=actualizacion, headers=_headers())

    assert respuesta.status_code == 200
    descargar_mock.assert_called_once_with("doc-1")

    guardadas = list((tmp_path / "boveda" / "30-imagenes").iterdir())
    assert len(guardadas) == 1
    assert guardadas[0].suffix == ".png"
    assert guardadas[0].read_bytes() == b"bytes-png"


def test_documento_que_no_es_imagen_se_ignora(cliente: TestClient) -> None:
    """Un PDF u otro adjunto en "document" no se toma como imagen."""
    salida_ambiguo = SalidaRouter(clase=Intencion.AMBIGUO, confianza=0.5)
    actualizacion = {
        "message": {
            "chat": {"id": CHAT_ID_AUTORIZADO},
            "document": {"file_id": "pdf-1", "mime_type": "application/pdf"},
        }
    }

    with (
        patch("app.main.descargar_archivo") as descargar_mock,
        patch("app.main.enviar_mensaje"),
        patch("grafo.nodos.router.ChatAnthropic") as router_mock,
    ):
        router_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            salida_ambiguo
        )

        respuesta = cliente.post("/webhook/telegram", json=actualizacion, headers=_headers())

    assert respuesta.status_code == 200
    descargar_mock.assert_not_called()


def test_nota_de_voz_se_transcribe_y_entra_al_grafo_como_texto(cliente: TestClient) -> None:
    """Fase 7.5: un audio se transcribe y el texto sigue el camino normal.

    No hay nodo nuevo: el Router clasifica el texto transcripto y el
    Archivista lo guarda como cualquier captura tipeada.
    """
    salida_captura = SalidaRouter(clase=Intencion.CAPTURAR, confianza=0.95)
    actualizacion = {
        "message": {
            "chat": {"id": CHAT_ID_AUTORIZADO},
            "voice": {"file_id": "voz-1", "mime_type": "audio/ogg", "duration": 3},
        }
    }

    with (
        patch("app.main.descargar_archivo") as descargar_mock,
        patch("app.main.transcribir") as transcribir_mock,
        patch("app.main.enviar_mensaje") as enviar_mock,
        patch("grafo.nodos.router.ChatAnthropic") as router_mock,
        patch("grafo.nodos.archivista.ChatAnthropic") as archivista_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.archivista.indexar_nota"),
    ):
        descargar_mock.return_value = b"bytes-del-audio"
        transcribir_mock.return_value = "acordate de comprar pan"
        router_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            salida_captura
        )
        archivista_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            NotaPropuesta(titulo="Comprar pan", tags=["compras"])
        )
        llamar_mock.return_value = ["00-inbox/comprar-pan.md"]

        respuesta = cliente.post("/webhook/telegram", json=actualizacion, headers=_headers())

    assert respuesta.status_code == 200
    descargar_mock.assert_called_once_with("voz-1")
    transcribir_mock.assert_called_once()
    assert transcribir_mock.call_args[0][0] == b"bytes-del-audio"

    # La prueba de que el texto transcripto entro al grafo: llego intacto
    # hasta el contenido de la nota que crea el Archivista.
    assert llamar_mock.call_args.kwargs["contenido"] == "acordate de comprar pan"

    enviar_mock.assert_called_once()


def test_corregir_mueve_la_nota_y_anota_el_caso(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/corregir re-archiva la nota mal clasificada y la suma al set de eval."""
    boveda = tmp_path / "boveda"
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(boveda))

    salida_captura = SalidaRouter(clase=Intencion.CAPTURAR, confianza=0.9)

    with (
        patch("grafo.nodos.router.ChatAnthropic") as router_mock,
        patch("grafo.nodos.archivista.ChatAnthropic") as archivista_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.archivista.indexar_nota"),
        patch("app.main.enviar_mensaje") as enviar_mock,
    ):
        router_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            salida_captura
        )
        archivista_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            NotaPropuesta(titulo="Llamar al contador", tags=["finanzas"])
        )
        # El mock de la tool MCP crea la nota de verdad en la boveda temporal,
        # para que /corregir tenga un archivo real que mover.
        llamar_mock.side_effect = lambda _nombre, **kw: [
            operaciones.crear_nota(
                kw["titulo"], kw["tags"], kw["contenido"], kw["carpeta"], kw["origen"]
            )
        ]

        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "tengo que llamar al contador el viernes"),
            headers=_headers(),
        )
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/corregir tarea"),
            headers=_headers(),
        )

    assert not (boveda / "00-inbox" / "llamar-al-contador.md").exists()
    assert (boveda / "20-tareas" / "llamar-al-contador.md").exists()

    correcciones = (boveda / "90-sistema" / "correcciones.jsonl").read_text(encoding="utf-8")
    assert '"intencion": "tarea"' in correcciones
    assert "llamar al contador" in correcciones

    _, texto_respuesta = enviar_mock.call_args_list[-1][0]
    assert "tarea" in texto_respuesta


def test_corregir_sin_intencion_muestra_el_uso(cliente: TestClient) -> None:
    with patch("app.main.enviar_mensaje") as enviar_mock:
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/corregir"),
            headers=_headers(),
        )

    _, texto = enviar_mock.call_args[0]
    assert "Uso: /corregir" in texto


def test_corregir_sin_corrida_previa_lo_dice(cliente: TestClient) -> None:
    with patch("app.main.enviar_mensaje") as enviar_mock:
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/corregir tarea"),
            headers=_headers(),
        )

    _, texto = enviar_mock.call_args[0]
    assert "nada que corregir" in texto


def _ahora() -> datetime:
    return datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def test_disparar_recordatorios_vencidos_envia_y_marca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    antes = _ahora() - timedelta(hours=1)
    almacen.agregar("comprar pan", _ahora() - timedelta(minutes=1), 999, antes)
    almacen.agregar("mas tarde", _ahora() + timedelta(hours=2), 999, _ahora())

    with patch("app.main.enviar_mensaje") as enviar_mock:
        disparados = _disparar_recordatorios_vencidos(_ahora())

    assert disparados == 1
    chat_id, texto = enviar_mock.call_args[0]
    assert chat_id == 999
    assert "comprar pan" in texto
    # El vencido salio de pendientes; el futuro sigue.
    assert [r.texto for r in almacen.pendientes()] == ["mas tarde"]


def test_proxima_ocurrencia_avanza_hasta_el_futuro() -> None:
    base = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)  # lunes
    ahora = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)  # ~2 semanas despues

    diaria = _proxima_ocurrencia(base, "diario", ahora)
    semanal = _proxima_ocurrencia(base, "semanal", ahora)

    assert diaria > ahora and diaria.hour == 9
    assert semanal > ahora and semanal.weekday() == 0  # sigue siendo lunes


def test_sumar_meses_recorta_el_dia() -> None:
    # 31 de enero + 1 mes -> 28 de febrero (2026 no es bisiesto).
    assert _sumar_meses(datetime(2026, 1, 31, tzinfo=UTC), 1) == datetime(2026, 2, 28, tzinfo=UTC)
    # cruce de anio
    assert _sumar_meses(datetime(2026, 12, 15, tzinfo=UTC), 1) == datetime(2027, 1, 15, tzinfo=UTC)


def test_disparar_recurrente_reprograma_en_vez_de_marcar_enviado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    almacen.agregar(
        "regar las plantas", _ahora() - timedelta(minutes=1), 999,
        _ahora() - timedelta(days=1), repetir="diario",
    )

    with patch("app.main.enviar_mensaje") as enviar_mock:
        _disparar_recordatorios_vencidos(_ahora())

    enviar_mock.assert_called_once()
    pend = almacen.pendientes()
    assert len(pend) == 1  # sigue pendiente, reprogramado
    assert pend[0].cuando_dt() > _ahora()


def test_armar_briefing_junta_recordatorios_de_hoy_y_listas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    monkeypatch.setenv("TZ_USUARIO", "UTC")
    hoy_local = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
    almacen.agregar("dentista", datetime(2026, 9, 8, 15, 0, tzinfo=UTC), 999, _ahora())
    almacen.agregar("otro mes", datetime(2026, 10, 1, 9, 0, tzinfo=UTC), 999, _ahora())
    operaciones.agregar_a_lista("compras", ["pan", "cafe"])

    texto = _armar_briefing(hoy_local)

    assert texto is not None
    assert "dentista" in texto and "15:00" in texto
    assert "otro mes" not in texto
    assert "compras (2)" in texto


def test_armar_briefing_vacio_devuelve_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    assert _armar_briefing(datetime(2026, 9, 8, 8, 0, tzinfo=UTC)) is None


def test_briefing_se_manda_una_vez_por_dia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    monkeypatch.setenv("TZ_USUARIO", "UTC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID_AUTORIZADO", "999")
    operaciones.agregar_a_lista("compras", ["pan"])

    antes_de_hora = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)
    en_hora = datetime(2026, 9, 8, 8, 30, tzinfo=UTC)

    with patch("app.main.enviar_mensaje") as enviar_mock:
        assert _enviar_briefing_si_toca(antes_de_hora) is False  # todavia no son las 8
        assert _enviar_briefing_si_toca(en_hora) is True  # primera vez del dia
        assert _enviar_briefing_si_toca(en_hora) is False  # ya se mando hoy

    assert enviar_mock.call_count == 1


def test_digest_se_manda_el_dia_de_la_semana_y_una_vez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    monkeypatch.setenv("TZ_USUARIO", "UTC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID_AUTORIZADO", "999")
    monkeypatch.setattr("app.main.DIA_DIGEST", 0)  # lunes
    monkeypatch.setattr("app.main.HORA_DIGEST", 9)
    operaciones.agregar_a_lista("compras", ["pan"])

    domingo = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)  # weekday() == 6
    lunes = datetime(2026, 9, 7, 9, 30, tzinfo=UTC)  # weekday() == 0

    with patch("app.main.enviar_mensaje") as enviar_mock:
        assert _enviar_digest_si_toca(domingo) is False  # no es el dia
        assert _enviar_digest_si_toca(lunes) is True  # primera vez de la semana
        assert _enviar_digest_si_toca(lunes) is False  # ya se mando

    assert enviar_mock.call_count == 1


def test_comando_digest_devuelve_el_repaso(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    operaciones.agregar_a_lista("compras", ["pan", "cafe"])

    with patch("app.main.enviar_mensaje") as enviar_mock:
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/digest"),
            headers=_headers(),
        )

    _, texto = enviar_mock.call_args[0]
    assert "Repaso semanal" in texto
    assert "compras (2)" in texto


def test_comando_recordatorios_lista_y_cancela(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    r = almacen.agregar(
        "pagar el alquiler", _ahora() + timedelta(days=1), CHAT_ID_AUTORIZADO, _ahora()
    )

    with patch("app.main.enviar_mensaje") as enviar_mock:
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/recordatorios"),
            headers=_headers(),
        )
        _, lista = enviar_mock.call_args[0]

        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, f"/cancelar {r.id}"),
            headers=_headers(),
        )
        _, cancelacion = enviar_mock.call_args[0]

    assert "pagar el alquiler" in lista
    assert r.id in lista
    assert "cancelado" in cancelacion.lower()
    assert almacen.pendientes() == []


def test_comando_recordatorios_vacio(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    with patch("app.main.enviar_mensaje") as enviar_mock:
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/recordatorios"),
            headers=_headers(),
        )

    _, texto = enviar_mock.call_args[0]
    assert "No tenes recordatorios" in texto


def test_comando_lista_nombra_y_muestra(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    operaciones.agregar_a_lista("compras", ["pan", "cafe"])

    with patch("app.main.enviar_mensaje") as enviar_mock:
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/lista"),
            headers=_headers(),
        )
        _, nombres = enviar_mock.call_args[0]

        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/lista compras"),
            headers=_headers(),
        )
        _, detalle = enviar_mock.call_args[0]

    assert "compras" in nombres
    assert "pan" in detalle and "cafe" in detalle


def test_comando_lista_sin_ninguna(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    with patch("app.main.enviar_mensaje") as enviar_mock:
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/lista"),
            headers=_headers(),
        )

    _, texto = enviar_mock.call_args[0]
    assert "Todavia no tenes ninguna lista" in texto


def test_comando_reindexar_llama_a_sincronizar(cliente: TestClient) -> None:
    with (
        patch("app.main.enviar_mensaje") as enviar_mock,
        patch("app.main.sincronizar_indice") as sync_mock,
    ):
        sync_mock.return_value = {"actualizadas": 3, "borradas": 1}
        cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/reindexar"),
            headers=_headers(),
        )

    sync_mock.assert_called_once()
    _, texto = enviar_mock.call_args[0]
    assert "3 nota" in texto and "1 borrada" in texto
