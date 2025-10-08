import os
import logging
from geopy.geocoders import Nominatim
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from math import radians, cos, sin, sqrt, atan2

TOKEN = os.getenv("TELEGRAM_TOKEN")
CITY_HINT = os.getenv("CITY_HINT")

geolocator = Nominatim(user_agent="be_route_bot")

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
    """Geocode an address using Nominatim."""
    query = address
    if CITY_HINT and CITY_HINT.lower() not in address.lower():
        query = f"{address}, {CITY_HINT}"
    location = geolocator.geocode(query, timeout=10)
    if not location:
        raise ValueError("Dirección no encontrada.")
    return (location.latitude, location.longitude)

def haversine(coord1, coord2):
    """Calculate the great-circle distance between two points."""
    R = 6371.0
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2)**2 + cos(phi1) * cos(phi2) * sin(dlambda / 2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def route_distance(route, points):
    """Compute the total distance of a route."""
    dist = 0
    for i in range(len(route) - 1):
        dist += haversine(points[route[i]], points[route[i + 1]])
    return dist

def nearest_neighbor(points, start_index=0):
    """Produce an initial route using a nearest neighbor heuristic."""
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
    """Improve a route using the 2-opt algorithm."""
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
    """Build Google Maps directions links in chunks."""
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
    """Process a message containing multiple addresses and return an optimized route."""
    if "depot" not in context.user_data:
        await update.message.reply_text("Primero establece un depósito con /depot o compartiendo tu ubicación.")
        return

    text = update.message.text.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    points = []
    labels = []

    # Add depot as first point
    points.append(context.user_data["depot"])
    labels.append("Depósito")

    # Geocode each provided address
    for line in lines:
        try:
            lat, lon = geocode(line)
            points.append((lat, lon))
            labels.append(line)
        except Exception as e:
            await update.message.reply_text(f"No se pudo geocodificar {line}: {e}")
            return

    # Generate initial route and optimize it
    route = nearest_neighbor(points, 0)
    optimized = two_opt(route, points)

    # Build response text
    order_lines = []
    for idx, stop_idx in enumerate(optimized):
        order_lines.append(f"{idx + 1}. {labels[stop_idx]}")
    response = "Orden de paradas optimizado:\n" + "\n".join(order_lines)

    # Build Google Maps directions links
    maps_links = build_maps_links([points[i] for i in optimized])
    for i, link in enumerate(maps_links):
        response += f"\n\nTramo {i + 1}: {link}"

    await update.message.reply_text(response)

def main():
    """Start the Telegram bot."""
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
