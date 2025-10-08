# BE_Route_Bot

Este repositorio contiene un bot de Telegram para optimizar rutas de entrega. Los operadores envían su ubicación de salida y una lista de domicilios, y el bot devuelve el orden optimizado y enlaces de Google Maps para cada tramo.

## Cómo usar

1. Crea un bot con @BotFather en Telegram y copia el token.
2. Ajusta las variables de entorno en `.env.example` y renómbralo a `.env` o configura variables de entorno en tu servicio de despliegue:
   - `TELEGRAM_TOKEN`: token de tu bot.
   - `CITY_HINT`: ciudad predeterminada para geocodificación (opcional).
3. Instala las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

4. Ejecuta el bot:

   ```bash
   python be_route_bot.py
   ```

## Despliegue

### Docker

```bash
docker build -t be-route-bot .
docker run -e TELEGRAM_TOKEN=tu_token -e CITY_HINT="CDMX" be-route-bot
```

### Railway/Render

Usa el `Procfile` y `render.yaml` para configurar un servicio tipo Worker. Asegúrate de establecer las variables de entorno necesarias.

## Funcionamiento

El bot geocodifica direcciones usando OpenStreetMap (Nominatim), aplica una heurística de vecino más cercano seguida de optimización 2-Opt y responde con el orden de entrega y enlaces de Google Maps divididos en tramos de hasta 10 paradas.
