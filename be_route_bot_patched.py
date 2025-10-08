import os
import logging
import re
from geopy.geocoders import Nominatim
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from math import radians, cos, sin, sqrt, atan2

# Optional Google Maps import
try:
    import googlemaps  # type: ignore
except ImportError:
    googlemaps = None

# Environment variables
TOKEN = os.getenv("TELEGRAM_TOKEN")
CITY_HINT = os.getenv("CITY_HINT")
GMAPS_KEY = os.getenv("GOOGLE_MAPS_KEY")
GEOCODER_PREF = os.getenv("GEOCODER_PREF", "any").lower()

# Initialize geocoders
geolocator = Nominatim(user_agent="be_route_bot")
gmaps = googlemaps.Client(key=GMAPS_KEY) if GMAPS_KEY and googlemaps else None

# Coordinate regex for detecting "lat, lon" input
coord_rx = re.compile(r"^\s*(-?\d{1,2}\.\d+)[,\s]+(-?\d{1,3}\.\d+)\s*$")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message and instructions."""
    await update.message.reply_text(
        "Bienvenido a BE Route Bot.\n"
        "Usa /depot <dirección> para establecer el punto de partida o comparte tu ubicación.\n"
        "Luego envía la lista de direcciones, una por línea, para optimizar la ruta."
    )

async def depot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the depot location from address or location."""
    if context.args:
        address = " ".join(context.args)
        try:
            lat, lon = geocode(address)
        except Exception as e:
            await update.message.reply_text(f"No se pudo geocodificar la dirección: {address}\n{e}")
            return
    elif update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
    else:
        await update.message.reply_text("Debes proporcionar una dirección después de /depot o compartir tu ubicación.")
        return
    context.user_data["depot"] = (lat, lon)
    await update.message.reply_text(f"Depósito establecido en ({lat:.5f}, {lon:.5f}). Envía las direcciones para optimizar.")


def geocode(address: str):
    """
    Geocode an address or coordinate string.

    1. Detect if the input looks like a pair of latitude/longitude coordinates
       (e.g. "20.56912,-100.42088"). If so, it returns those values directly.
    2. Otherwise, it will append the CITY_HINT to the query if not already present
       and attempt to geocode using OpenStreetMap's Nominatim.
    3. If Nominatim fails and a valid Google Maps API key is configured, it
       will attempt to geocode using Google. The order of geocoders can be
       controlled via the GEOCODER_PREF environment variable.

    :param address: The address or coordinate string to geocode.
    :returns: A tuple of (latitude, longitude).
    :raises ValueError: If no geocoder returns a result.
    """
    # 1. Check coordinates
    match = coord_rx.match(address)
    if match:
        lat = float(match.group(1))
        lon = float(match.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return (lat, lon)
    # 2. Append city hint if needed
    query = address
    if CITY_HINT and CITY_HINT.lower() not in address.lower():
        query = f"{address}, {CITY_HINT}"
    # Determine order
    if GEOCODER_PREF == "google":
        order = ["google", "osm"]
    elif GEOCODER_PREF == "osm":
        order = ["osm", "google"]
    else:
        order = ["osm", "google"]
    # Try geocoders
    for which in order:
        if which == "osm":
            try:
                location = geolocator.geocode(query, timeout=10)
            except Exception:
                location = None
            if location:
                return (location.latitude, location.longitude)
        if which == "google" and gmaps:
            try:
                results = gmaps.geocode(query, region="mx")
            except Exception:
                results = None
            if results:
                loc = results[0]["geometry"]["location"]
                return (loc["lat"], loc["lng"])
    raise ValueError("Dirección no encontrada.")


def haversine(coord1, coord2):
    R = 6371.0
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2)**2 + cos(phi1) * cos(phi2) * sin(dlambda / 2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def route_distance(route, points):
    dist = 0
    for i in range(len(route) - 1):
        dist += haversine(points[route[i]], points[route[i + 1]])
    return dist


def nearest_neighbor(points, start_index=0):
    unvisited = list(range(len(points)))
    path = [start_index]
    unvisited.remove(start_index)
    current = start_index
    while unvisited:
        next_idx = min(unvisited, key=lambda i: haversine(points[current], points[i]))
        path.append(next_idx)
        unvisited.remove(next_idx)
        current = next_idx
    return path


def two_opt(route, points):
    best = route
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best)):
                if j - i == 1:
                    continue
                new_route = best[:i] + best[i:j][::-1] + best[j:]
                if route_distance(new_route, points) < route_distance(best, points):
                    best = new_route
                    improved = True
        route = best
    return best


def build_maps_links(points):
    links = []
    base = "https://www.google.com/maps/dir/?api=1"
    chunk_size = 10
    for idx in range(0, len(points), chunk_size):
        chunk = points[idx:idx + chunk_size]
        origin = f"{chunk[0][0]},{chunk[0][1]}"
        dest = f"{chunk[-1][0]},{chunk[-1][1]}"
        if len(chunk) > 2:
            waypoints = "|".join([f"{p[0]},{p[1]}" for p in chunk[1:-1]])
            url = f"{base}&origin={origin}&destination={dest}&waypoints={waypoints}"
        else:
            url = f"{base}&origin={origin}&destination={dest}"
        links.append(url)
    return links


async def handle_addresses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "depot" not in context.user_data:
        await update.message.reply_text("Primero establece un depósito con /depot o compartiendo tu ubicación.")
        return
    text = update.message.text.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    points = []
    labels = []
    # Add depot first
    points.append(context.user_data["depot"])
    labels.append("Depósito")
    # Geocode each provided line
    for line in lines:
        try:
            lat, lon = geocode(line)
            points.append((lat, lon))
            labels.append(line)
        except Exception as e:
            await update.message.reply_text(f"No se pudo geocodificar {line}: {e}")
            return
    route = nearest_neighbor(points, 0)
    optimized = two_opt(route, points)
    order_lines = []
    for idx, stop_idx in enumerate(optimized):
        order_lines.append(f"{idx + 1}. {labels[stop_idx]}")
    response = "Orden de paradas optimizado:\n" + "\n".join(order_lines)
    maps_links = build_maps_links([points[i] for i in optimized])
    for i, link in enumerate(maps_links):
        response += f"\n\nTramo {i + 1}: {link}"
    await update.message.reply_text(response)


def main():
    logging.basicConfig(level=logging.INFO)
    if not TOKEN:
        raise RuntimeError("Debe definir la variable de entorno TELEGRAM_TOKEN.")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("depot", depot))
    app.add_handler(MessageHandler(filters.LOCATION, depot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_addresses))
    app.run_polling()


if __name__ == "__main__":
    main()
