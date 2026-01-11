# 🛍️ CazaChollos

System to monitor Telegram channels for deals, store them in a PostgreSQL database, and display them in a real-time dashboard.

## 📋 Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop/)
- [Git](https://git-scm.com/)

## 🚀 Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd cazachollos
    ```

2.  **Environment Configuration:**
    Copy the example environment file and fill in your Telegram API credentials.
    ```bash
    cp .env.example .env
    ```
    > **Note:** You need a `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from [my.telegram.org](https://my.telegram.org).

3.  **Start the Services:**
    Run the application using Docker Compose.
    ```bash
    docker-compose up -d --build
    ```

4.  **Initialize the Database (Critical Step):**
    On the first run, you must manually apply the database migrations to create the necessary tables.
    ```bash
    docker exec cazachollos_ingestor alembic upgrade head
    ```

## 📊 Usage

Once the services are running and the database is initialized:

-   **Dashboard:** Open [http://localhost:8501](http://localhost:8501) in your browser.
-   **Logs:** View logs to monitor activity:
    ```bash
    docker-compose logs -f
    ```

## 🛠️ Troubleshooting

**Error: `relation "deals" does not exist`**
This means the database migrations haven't been run. Execute the initialization command from step 4.
