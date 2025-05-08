## Running This Project with Docker

This project includes a Docker setup for running a Python (Flask) web application. Below are the instructions and details specific to this project:

### Project-Specific Docker Details
- **Python Version:** 3.11 (as specified in the Dockerfile)
- **Dependencies:** Installed from `requirements.txt` (ensure this file is up to date with your app's requirements)
- **App Entrypoint:** `app.py` (Flask application)
- **Templates:** HTML templates are located in the `Templates/` directory and are copied into the Docker image.

### Environment Variables
- The following environment variables are set by default in the Dockerfile:
  - `FLASK_APP=app.py`
  - `FLASK_RUN_HOST=0.0.0.0`
- If you need to provide additional environment variables (e.g., secrets, configuration), you can create a `.env` file and uncomment the `env_file` line in the `docker-compose.yml`.

### Build and Run Instructions
1. **Build and start the application:**
   ```sh
   docker compose up --build
   ```
   This will build the Docker image and start the Flask app in a container named `python-app`.

2. **Access the application:**
   - The Flask app will be available at [http://localhost:5000](http://localhost:5000) on your host machine.

### Ports
- **5000:** Exposed by the container and mapped to the host (Flask default port).

### Special Configuration
- The Dockerfile creates a non-root user (`appuser`) for running the application, enhancing security.
- If your application requires a database or other services, you can extend the `docker-compose.yml` by adding new services and configuring `depends_on` as needed.

---

*This section was updated to reflect the current Docker-based setup for this project. For further details on the application, refer to the rest of this README and the project documentation.*
