# CampusLoop

**Share the route. Split the cost. Ride together.**

CampusLoop is a student-focused carpooling platform designed to make transportation more affordable, convenient, and accessible within university communities.

Unlike traditional ride-hailing services, CampusLoop connects students who are already planning to travel in similar directions. Both riders and drivers can post upcoming trips, discover compatible routes, and coordinate shared journeys.

Initially developed for the **University of Southern California (USC)** community, CampusLoop aims to expand into a connected transportation network across universities.

## Features

### Ride Sharing & Matching
- **Two-Way Ride Posting:** Both riders and drivers can create trip postings.
- **One-Time Trips:** Find or offer rides for airport transfers, concerts, weekend outings, and other occasional journeys.
- **Recurring Trips:** Coordinate regular commutes to campus, classes, or internships.
- **Route-Based Matching:** Discover compatible trips based on locations, departure schedules, and available seats.
- **Ride Management:** Send, accept, and manage ride requests and confirmations.
- **Flexible Roles:** Use one account as both a rider and a driver.

### Smart Pricing
- Distance- and travel-time-based cost estimation
- Rider-count-based pricing adjustments
- Estimated earnings ranges for drivers
- Estimated cost-sharing ranges for riders
- Transparent pricing without surge multipliers

### Maps & Navigation
- Interactive maps powered by OpenStreetMap data
- Location selection for pickup and drop-off
- Route distance and travel-time estimation through Google Maps Routes API
- Route visualization to support trip planning

### AI-Powered Assistance
- AI chatbot powered by Ollama
- Natural-language assistance for navigating and understanding CampusLoop
- Locally hosted language models

### Student Community
- University email-based account registration
- Campus-focused ride discovery
- Shared transportation within student communities

---

## Tech Stack

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python |
| Database | SQLite |
| Map Visualization | OpenStreetMap |
| Routing & Travel Estimation | Google Maps Routes API |
| AI Chatbot | Ollama |
| Containerization | Docker, Docker Compose |
| Version Control | Git, GitHub |

---

## Project Structure

```text
CampusLoop/
├── app/                  # Python backend
│   ├── server.py
│   ├── routes.py         # Routing and pricing logic
│   └── ...
├── static/               # Frontend assets
│   ├── index.html
│   ├── app.js
│   ├── landing.js
│   ├── landing.css
│   ├── style.css
│   └── ...
├── tests/                # Automated tests
├── knowledge/            # Application knowledge resources
├── compose.yaml          # Docker Compose configuration
├── Dockerfile
├── requirements.txt
├── .env.example          # Environment variable template
└── README.md
```

---

## Getting Started

### Prerequisites

Install the following tools before running the application locally:

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- A code editor, such as [Visual Studio Code](https://code.visualstudio.com/)

A Google Maps API key is required to enable Google Maps Routes API functionality.

### 1. Clone the Repository

```bash
git clone <REPOSITORY_URL>
cd <REPOSITORY_DIRECTORY>
```

All subsequent commands should be executed from the project root directory containing `compose.yaml`.

### 2. Configure Environment Variables

Copy the example environment configuration:

```bash
cp .env.example .env
```

Open `.env` and add your Google Maps API key:

```dotenv
GOOGLE_MAPS_API_KEY=YOUR_ACTUAL_API_KEY
```

If `.env` already exists, update the existing file instead.

**Security:** Never commit `.env` or API credentials to GitHub. Ensure `.env` is included in `.gitignore`.

For instructions on obtaining an API key, see [Google Maps Routes API Setup](#google-maps-routes-api-setup).

### 3. Build and Run

Make sure Docker Desktop is running.

From the project root, execute:

```bash
HEKY_PORT=8010 docker compose up --build -d
```

This command builds and starts the application's Docker services in the background.

### 4. Access the Application

Open your browser and navigate to:

**http://localhost:8010**

To verify that the containers are running:

```bash
HEKY_PORT=8010 docker compose ps
```

The application and Ollama services should appear in the container list.

---

## External Services & APIs

CampusLoop integrates several mapping, routing, and AI technologies to support ride planning and user assistance.

### Google Maps Routes API

The Google Maps Routes API provides information used for route planning and cost estimation.

Its capabilities include:

- Driving distance between two locations
- Estimated travel duration
- Traffic-aware travel-time estimates
- Route information for calculating suggested cost sharing

#### Google Maps Routes API Setup

**Step 1 — Obtain an API Key**

1. Visit the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a Google Cloud project.
3. Enable billing as required by Google Maps Platform.
4. Navigate to **APIs & Services → Library**.
5. Search for and enable **Routes API**.
6. Navigate to **APIs & Services → Credentials**.
7. Select **Create Credentials → API Key**.
8. Copy the generated key and configure appropriate API restrictions.

Google Maps Platform usage may incur charges depending on API usage and available credits.

**Step 2 — Configure the Environment**

In the project root, copy `.env.example` to `.env` if you haven't already.

Add:

```dotenv
GOOGLE_MAPS_API_KEY=YOUR_ACTUAL_API_KEY
```

In `compose.yaml`, keep the following environment configuration unchanged:

```yaml
GOOGLE_MAPS_API_KEY: "${GOOGLE_MAPS_API_KEY:-}"
```

This passes the API key from your local environment into the application container.

**Step 3 — Rebuild Docker**

After updating the environment variables, run:

```bash
HEKY_PORT=8010 docker compose up -d --build app
```

**Step 4 — Verify**

Navigate to:

**http://127.0.0.1:8010**

Refresh the application and test route estimation by entering pickup and destination locations when creating a ride.

If the integration does not work, verify the API key, billing configuration, enabled APIs, and container logs.

### OpenStreetMap

[OpenStreetMap](https://www.openstreetmap.org/) provides open geographic data used for CampusLoop's interactive maps.

The mapping interface supports:

- Viewing geographic locations
- Selecting pickup and drop-off points
- Exploring streets and surrounding areas
- Visualizing trip locations and routes

OpenStreetMap provides geographic data; map rendering and routing may rely on additional libraries or services.

### Ollama — AI Chatbot

[Ollama](https://ollama.com/) enables CampusLoop to run a large language model locally.

The AI chatbot provides conversational assistance to help users understand the platform and its functionality.

**Benefits of local AI inference:**

- No external hosted LLM API key required
- Greater control over the model environment
- Local processing of chatbot requests
- Integration with the existing Docker infrastructure

#### Ollama Setup

Ollama is configured as a service in Docker Compose.

Start the services:

```bash
HEKY_PORT=8010 docker compose up -d --build
```

Check the Ollama container:

```bash
HEKY_PORT=8010 docker compose ps
```

View Ollama logs:

```bash
HEKY_PORT=8010 docker compose logs -f ollama
```

The chatbot requires a compatible Ollama model to be installed and available.

To check which models are installed:

```bash
HEKY_PORT=8010 docker compose exec ollama ollama list
```

If the configured model is missing, pull it into the container using:

```bash
HEKY_PORT=8010 docker compose exec ollama ollama pull <MODEL_NAME>
```

Replace `<MODEL_NAME>` with the model configured for your application's chatbot.

---

## Pricing Algorithm

CampusLoop's proposed pricing model is designed around transparent cost sharing rather than traditional ride-hailing or surge pricing.

The model considers:

1. Route distance
2. Estimated travel duration
3. Number of participating riders

### 1. Base Price

The base price is calculated using distance and travel duration:

**Base Price = Distance × Rate per Mile + Time × Rate per Minute**

| Parameter | Value |
|---|---|
| Rate per mile | $0.60/mile |
| Rate per minute | $0.30/minute |
| Service fee | None (initially) |

Distance and duration can be obtained through the Google Maps Routes API.

### 2. Driver Earnings

Driver earnings increase as more riders join the trip.

**Driver Earnings = Base Price × [1 + 0.65 × (n − 1)]**

Where `n` is the number of confirmed riders.

| Riders | Driver Earnings Multiplier |
|---|---|
| 1 | 1.00× |
| 2 | 1.65× |
| 3 | 2.30× |
| 4 | 2.95× |

### 3. Rider Contribution

The driver's total earnings are divided equally among confirmed riders.

**Price per Rider = Driver Earnings ÷ n**

As the number of riders increases:

- Total driver earnings increase.
- Individual rider contributions decrease.
- The trip becomes more cost-efficient for participants.

### 4. Price Estimates

The intended pricing interface provides estimated ranges before a ride is confirmed.

**For Drivers**

Estimated earnings range from one confirmed rider to all available seats being filled.

**For Riders**

Estimated individual contributions range from traveling alone to sharing the ride with the maximum number of riders.

After a ride match is accepted, the price is recalculated based on the number of confirmed riders.

**Implementation status:** This section describes the proposed rider-count-based algorithm. The backend's older distance-only pricing implementation may still need to be migrated to this model.

---

## Development

### Docker Commands

| Action | Command |
|---|---|
| Build and start all services | `HEKY_PORT=8010 docker compose up --build -d` |
| Start existing containers | `HEKY_PORT=8010 docker compose up -d` |
| Rebuild application only | `HEKY_PORT=8010 docker compose up -d --build app` |
| Check container status | `HEKY_PORT=8010 docker compose ps` |
| View application logs | `HEKY_PORT=8010 docker compose logs -f app` |
| View Ollama logs | `HEKY_PORT=8010 docker compose logs -f ollama` |
| Restart application | `HEKY_PORT=8010 docker compose restart app` |
| Stop services | `HEKY_PORT=8010 docker compose down` |

### Troubleshooting

**Website is not accessible**

Check whether the containers are running:

```bash
HEKY_PORT=8010 docker compose ps
```

Inspect application logs:

```bash
HEKY_PORT=8010 docker compose logs --tail=100 app
```

**Changes are not appearing**

Rebuild the application:

```bash
HEKY_PORT=8010 docker compose up -d --build app
```

Then hard-refresh the browser:

- macOS: `Cmd + Shift + R`
- Windows: `Ctrl + Shift + R`

**Port 8010 is already in use**

Check the process using the port:

```bash
lsof -i :8010
```

Stop the conflicting service or configure a different host port.

**Google Maps Routes API is not working**

Check that:

- The API key is present in `.env`.
- Routes API is enabled in Google Cloud.
- Billing is configured correctly.
- API key restrictions allow the required requests.
- The Docker application container was rebuilt after changing `.env`.

**AI chatbot is not responding**

Verify that the Ollama container is running:

```bash
HEKY_PORT=8010 docker compose ps
```

Check the installed models:

```bash
HEKY_PORT=8010 docker compose exec ollama ollama list
```

Review Ollama logs for errors:

```bash
HEKY_PORT=8010 docker compose logs --tail=100 ollama
```

Make sure the configured model is available and the host has sufficient memory to run it.

---

## Roadmap

CampusLoop's initial focus is on USC students, with plans to expand functionality and support a broader university community.

### University Expansion
Expand from USC to additional universities, starting with Southern California and eventually supporting students nationwide.

### Multi-Stop Ride Matching
Allow drivers to pick up multiple passengers along their planned routes, improving convenience and increasing seat utilization.

### Event-Based Ride Discovery
Enable users to name rides and associate them with searchable events, such as concerts, sporting events, and campus activities.

### Trust & Safety
Enhance the student community with stronger identity verification, safety features, and rider and driver feedback.

### Improved Matching
Develop more advanced route-overlap detection, departure-time flexibility, and personalized ride recommendations.

### Transit Integration
Explore connections with campus shuttle systems and public transportation to create more flexible mobility options.

---

## Project Vision

CampusLoop aims to make student transportation more accessible by connecting people whose travel plans already overlap.

By encouraging shared journeys, the platform seeks to reduce individual transportation costs, make better use of available vehicle capacity, and strengthen connections within university communities.

**One campus today. A connected student network tomorrow.**
