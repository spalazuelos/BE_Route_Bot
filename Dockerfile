# Use an official lightweight Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Define environment defaults (can be overridden at runtime)
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "be_route_bot.py"]
