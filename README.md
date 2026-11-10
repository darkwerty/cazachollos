# CazaChollos

Los grupos de ofertas de Telegram son un río de mensajes repetidos y sin estructura. CazaChollos los escucha,
saca de cada mensaje el producto, el precio, la tienda y el enlace limpio, descarta los repetidos y lo guarda en
PostgreSQL para poder buscar «auriculares sony» y ver esas ofertas, sin duplicados y con las mejores arriba.

## Cómo funciona

```
Grupos de Telegram ──► ingestor ──► PostgreSQL ◄── bot de Telegram (/buscar)
 (o un JSONL)          parser          (FTS)    ◄── panel en Streamlit (:8501)
```

1. **Ingesta.** Un cliente de Telegram (Telethon) escucha los grupos elegidos. Para probarlo sin Telegram, el
   mismo servicio puede reproducir un fichero JSONL de mensajes con sus tiempos (modo `REPLAY`).
2. **Extracción.** Reglas fijas sacan el enlace (quitando `utm_*`, `tag`, `ref` y acortando Amazon a `/dp/ID`),
   el precio y el precio anterior, la tienda, la categoría y un título limpio. Si hay clave de Gemini, un LLM
   extrae lo mismo en **salida estructurada** validada con Pydantic; si falla, se sale de rango o no está seguro
   del título, mandan las reglas.
3. **Deduplicación.** Hash del enlace limpio, el precio y el principio del título: la misma oferta publicada en
   dos canales se guarda una vez.
4. **Puntuación.** De 0 a 100 con una fórmula propia: el descuento y palabras como «mínimo histórico» o «error
   de precio» suben; «reacondicionado» o «usado» bajan. Un mensaje sin precio no cuenta como gratis.
5. **Búsqueda.** Búsqueda de texto completo de PostgreSQL en español (`websearch_to_tsquery`), ordenada por
   relevancia y puntuación, desde el bot y desde el panel.

Además se guarda cada mensaje original (`raw_messages`) para auditar lo que hace el parser.

## Probarlo en 2 minutos (sin Telegram)

Necesitas Docker.

```bash
git clone https://github.com/darkwerty/cazachollos.git
cd cazachollos
cp .env.example .env
docker compose up -d --build
```

Abre http://localhost:8501. El ingestor aplica las migraciones, reproduce `replay_data.jsonl` (12 mensajes
**inventados** que imitan los de un canal de ofertas, con un repetido, uno sin precio y uno que no es una
oferta) y termina. En el panel puedes buscar, por ejemplo, `auriculares` o `"freidora de aire"`.

## Con Telegram de verdad

1. Saca `TELEGRAM_API_ID` y `TELEGRAM_API_HASH` en https://my.telegram.org y ponlos en `.env`.
2. Pon `INGESTION_MODE=LIVE` y, en `TELEGRAM_ALLOWED_GROUPS`, los grupos que quieres escuchar (id o nombre).
3. La primera vez hay que iniciar sesión con tu número y el código que te manda Telegram:

   ```bash
   docker compose run --rm ingestor
   ```

   La sesión se guarda en el volumen `telegram_session` y después ya no lo vuelve a pedir:
   `docker compose up -d`.
4. Para el bot, crea uno con @BotFather, pon `BOT_TOKEN` en `.env` y arráncalo con
   `docker compose --profile bot up -d`. Responde en privado a `/buscar <producto>` o a cualquier texto.

El fichero de sesión equivale a tu cuenta de Telegram: no lo compartas. Git y Docker lo ignoran.

## LLM

Opcional. Con `GEMINI_API_KEY` se usa `GEMINI_MODEL` (por defecto `gemini-3.5-flash-lite`, un modelo barato pensado
para extraer datos en volumen). El mensaje va marcado como dato y no como instrucción, y la respuesta tiene que
cumplir el esquema de `DealExtraction` (`src/services/llm_services.py`): si no, se descarta entera.

## Desarrollo

```bash
poetry install
poetry run pytest -q
poetry run ruff check . && poetry run ruff format --check .
```

Los tests no necesitan base de datos, Telegram ni Gemini (el LLM se sustituye por dobles). GitHub Actions pasa
lint y tests en cada push.

Para ejecutar fuera de Docker: `poetry run alembic upgrade head`, `poetry run python cmd/run_ingestor.py` y
`poetry run streamlit run app.py`, con PostgreSQL en `POSTGRES_HOST`.

## Estructura

```
cmd/               puntos de entrada: ingestor y bot
src/domain/        modelos SQLAlchemy, esquemas Pydantic y la interfaz de las fuentes de mensajes
src/infrastructure/ base de datos, cliente de Telegram y fuentes LIVE y REPLAY
src/services/      parser, LLM, ingestor, búsqueda y bot
src/web/           consultas del panel
app.py             panel de Streamlit
migrations/        Alembic
scripts/           exportar mensajes guardados a JSONL (replay_privado.jsonl, fuera de git) y demo del replay
docs/              especificación inicial del MVP
```

## Límites

- La extracción por reglas está pensada para mensajes en español con el formato habitual de los canales de
  ofertas; con formatos raros el título o el precio pueden salir mal (para eso está el LLM).
- La puntuación es orientativa: con descuentos grandes y varias palabras clave se satura en 100.
- Escuchar grupos con una cuenta de usuario tiene que respetar las condiciones de Telegram y de cada grupo.
