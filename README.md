# E-Commerce Microservices

A complete **E-Commerce Microservices application** built using **Python, Flask, PostgreSQL, REST APIs, API Gateway, and a web frontend**.

The project demonstrates how independent microservices communicate with each other and how an API Gateway provides a single entry point for clients.

---

## 🚀 Features

* User Microservice
* Product Microservice
* Order Microservice
* API Gateway
* PostgreSQL database
* RESTful APIs
* Amazon Cognito authentication with Authorization Code + PKCE
* Product stock management
* Order creation and validation
* Microservice-to-microservice communication
* Frontend dashboard
* CORS support
* Environment-based configuration
* Git/GitHub ready

---

## 🏗️ Architecture

```text
                         Browser
                            |
                            v
                    Frontend :5500
                            |
                            v
                  API Gateway :5000
                     /      |      \
                    /       |       \
                   v        v        v
             User :5002  Product :5001  Order :5003
                 |           |            |
                 v           v            v
             PostgreSQL  PostgreSQL   PostgreSQL
```

### Order Flow

```text
Client
  |
  v
API Gateway
  |
  v
Order Service
  |
  +----> User Service
  |          |
  |          v
  |      Verify User
  |
  +----> Product Service
             |
             v
         Verify Product
             |
             v
         Check Stock# Task: Investigate the Existing Project and Develop the Kubernetes Investigation Backend

You are a senior Python/FastAPI developer, Kubernetes engineer, and security-focused software architect helping our student team build an **AI-Powered Kubernetes Security Investigation Platform**.

We have already deployed an e-commerce microservices application on K3s and installed Prometheus and Grafana.

We are now starting the development of the investigation platform.

**Your immediate objective is to investigate our existing files and infrastructure, propose the backend architecture, and then, after approval, implement the first working FastAPI backend connected to Kubernetes.**

## 1. Development environment

I am using:

- Windows as my main computer.
- VS Code and Codex through Remote SSH.
- Ubuntu 24.04 running inside VMware.
- An existing single-node K3s cluster on Ubuntu.
- Python for backend development.

The project is located at:

`/home/wejden/k8s_project`

**All development must happen on the Ubuntu VM through the remote VS Code workspace.**

The Ubuntu folder is our source of truth. I may maintain a separate Windows copy for viewing and backup, but do not automatically synchronize or modify it.

Do not install K3s in WSL, replace the cluster, or redeploy the existing application.

## 2. Existing infrastructure

Our e-commerce application includes:

- Flask frontend on port 5500
- API Gateway on port 5000
- User Service on port 5002
- Product Service on port 5001
- Order Service on port 5003
- PostgreSQL on port 5432

The application is deployed in Kubernetes namespace `ecommerce`.

We already have:

- Kubernetes Deployments and Services
- PostgreSQL StatefulSet and persistent storage
- Traefik Ingress
- Prometheus
- Grafana
- kube-state-metrics
- node-exporter

Monitoring components are in namespace `monitoring`.

Loki, Grafana Alloy, Falco, and the LLM investigation agent are planned but not implemented yet.

The VM has previously experienced CPU and memory pressure. Verify the current status before assuming the monitoring stack is healthy.

## 3. Important safety requirements

We previously encountered Git confusion because the e-commerce project has a nested `.git` repository.

For this task:

- Do not execute Git operations that change repository state, including `add`, `commit`, `push`, `reset`, `clean`, `switch`, or branch creation.
- Do not delete, move, or overwrite the existing e-commerce application.
- Do not modify the existing Kubernetes manifests or Helm releases without approval.
- Do not restart or delete running Pods.
- Do not deploy additional infrastructure yet.
- Do not expose the Kubernetes API publicly.
- Do not print or commit passwords, tokens, `.env` values, SSH keys, kubeconfig contents, or Kubernetes Secret data.
- Do not modify the existing React frontend in this milestone.
- Do not copy Kubernetes administrator credentials into the project.
- Keep Kubernetes operations read-only.

GitHub integration will be handled separately.

## 4. PHASE A — Investigate the existing project

**Start with read-only inspection. Do not write code yet.**

Inspect `/home/wejden/k8s_project` to identify:

1. Existing directories and project components.
2. Whether a FastAPI backend already exists.
3. Whether any Kubernetes Python client integration already exists.
4. The e-commerce application's Docker Compose and Kubernetes deployment configurations.
5. The existing monitoring Helm values and Ingress definitions.
6. Existing Python dependencies and tests.
7. Existing frontend API expectations.
8. The best location for our investigation backend.

Inspect the running cluster using safe, read-only commands where available:

```bash
sudo systemctl is-active k3s
sudo k3s kubectl get nodes
sudo k3s kubectl get namespaces
sudo k3s kubectl get pods -n ecommerce
sudo k3s kubectl get pods -n monitoring
```

If these commands require interactive sudo authentication, ask me to run them rather than requesting passwords or bypassing permissions.

Check how the existing user can access Kubernetes without exposing credential files.

If the current kubeconfig has administrator privileges, explain the implications and propose a dedicated read-only RBAC identity for future integration. Do not create it automatically.

### Deliverable A

Before making changes, report:

- Current project structure
- Existing application and monitoring components
- Current Kubernetes status, if accessible
- Existing backend code, if any
- Recommended backend directory
- Proposed file structure
- Dependencies required
- Security considerations
- Implementation plan

**STOP after the investigation and wait for my approval before implementing anything.**

## 5. PHASE B — Implement the FastAPI backend after approval

Build the first version using:

- Python 3
- FastAPI
- Uvicorn
- Official Kubernetes Python client
- Pydantic models
- Pytest for tests

Reuse existing backend code if appropriate. Do not duplicate an existing service.

Design a clear, modular structure, for example:

```text
investigation-backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   └── routes/
│   │       ├── health.py
│   │       └── kubernetes.py
│   ├── services/
│   │   └── kubernetes_service.py
│   └── schemas/
│       └── kubernetes.py
├── tests/
├── requirements.txt
└── README.md
```

This is a proposed structure. Adapt it if you find an existing backend or a better established project convention.

### Initial endpoints

**GET /api/health**

Return the backend's status without depending on Kubernetes availability.

**GET /api/namespaces**

List Kubernetes namespaces.

**GET /api/pods?namespace=ecommerce**

Return the real Pods in the requested namespace, including:

- Name
- Namespace
- Phase
- Node
- Readiness
- Container states
- Restart counts
- Waiting reasons
- Current and previous termination reasons when available

**GET /api/pods/{namespace}/{pod_name}/diagnostics**

Return structured diagnostic evidence:

- Pod metadata
- Pod conditions
- Container states
- Restart counts
- Last termination state
- Related Kubernetes events
- Recent container logs

For logs, use a reasonable maximum line count and response size. Support Pods with multiple containers and handle unavailable logs gracefully.

The backend must only collect and expose evidence. Do not invent root causes or pretend an LLM is already implemented.

### Kubernetes integration requirements

- Use the official Kubernetes Python client.
- Respect `KUBECONFIG` or the local Kubernetes client configuration.
- Support future in-cluster authentication when we deploy the backend inside Kubernetes.
- Avoid hard-coded credentials or IP addresses.
- Use read-only Kubernetes API calls.
- Handle missing Pods, invalid namespaces, permission failures, connection failures, and timeouts.
- Avoid exposing sensitive credentials or full internal exceptions to API clients.
- Bind Uvicorn to `127.0.0.1` by default.
- Keep the backend accessible from Windows through VS Code SSH port forwarding.

For this local prototype, investigate the safest available way to access K3s. Prefer an appropriately scoped read-only identity. Do not automatically grant new permissions or copy administrator credentials.

## 6. Tests

After implementation:

1. Verify imports and Python syntax.
2. Run automated tests with mocked Kubernetes responses.
3. Test `/api/health`.
4. Test namespace listing.
5. Test Pod listing.
6. Test diagnostics for healthy and failing Pod states.
7. Test API error handling.
8. Where permissions allow, test against the real `ecommerce` namespace.

Do not create deliberately failing Pods or alter existing workloads during this milestone.

Clearly report which tests passed and which could not be run.

## 7. Documentation

Document:

- Project structure and responsibilities
- Backend setup on Ubuntu
- Python virtual environment creation
- Dependency installation
- Safe Kubernetes authentication
- Running Uvicorn
- Accessing the API through VS Code port forwarding
- Swagger documentation at `http://localhost:8000/docs`
- Testing the API
- Known limitations and future integrations

## 8. Future architecture — plan only

Our eventual platform will integrate:

- Prometheus for metrics
- Loki and Grafana Alloy for logs
- Falco for runtime security alerts
- An LLM tool-calling investigation agent
- A frontend dashboard
- Human-approved remediation with auditable, limited Kubernetes permissions

Do not implement these components in the first backend milestone.

Design the backend so we can add them later without major restructuring.

## 9. How you should work with me

I want to understand every development step.

Follow this process:

1. Inspect the repository.
2. Explain what already exists.
3. Propose the smallest practical backend architecture.
4. List exactly which files you intend to create or modify.
5. Stop and ask for approval.
6. After approval, implement one component at a time.
7. Explain what each component does.
8. Run tests and report actual results.
9. Provide exact commands to launch the backend from Ubuntu.
10. Do not run any Git commit or push commands.

### Start now

Begin with **PHASE A: repository and K3s investigation**.

Your first response must include a clear analysis of the existing project and an implementation plan.

**Do not modify any files until I approve your plan.**

             |
             v
        Reduce Stock
             |
             v
        Create Order
```

---

## 🛠️ Technologies

### Backend

* Python
* Flask
* Flask-SQLAlchemy
* REST API
* Requests

### Database

* PostgreSQL
* SQLAlchemy ORM

### Authentication

* Verified Cognito access tokens

### Frontend

* HTML
* CSS
* JavaScript
* Flask

### Development Tools

* Git
* GitHub
* PowerShell
* VS Code

---

## 📁 Project Structure

```text
ecommerce-microservices/
│
├── api_gateway/
│   ├── app.py
│   └── .env
│
├── user_services/
│   ├── app.py
│   └── .env
│
├── product_services/
│   ├── app.py
│   └── .env
│
├── order_service/
│   ├── app.py
│   └── .env
│
├── front_end/
│   ├── app.py
│   │
│   ├── templates/
│   │   └── index.html
│   │
│   └── static/
│       ├── app.js
│       └── styles.css
│
├── .gitignore
├── README.md
└── requirements.txt
```

> `.env` files contain secrets and should not be committed to GitHub.

---

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/ecommerce-microservices.git
```

```bash
cd ecommerce-microservices
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

If `requirements.txt` is not available:

```bash
pip install Flask Flask-SQLAlchemy psycopg2-binary python-dotenv requests flask-cors
```

---

## 🗄️ PostgreSQL Setup

Create the required PostgreSQL databases:

```sql
CREATE DATABASE ecommerce_user_db;

CREATE DATABASE ecommerce_product_db;

CREATE DATABASE ecommerce_order_db;
```

Configure each service's `.env` file.

Example:

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/ecommerce_user_db
COGNITO_REGION=your-region
COGNITO_USER_POOL_ID=your-user-pool-id
COGNITO_CLIENT_ID=your-public-app-client-id
```

Use the appropriate database name for each service.

### Product Service

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/ecommerce_product_db
COGNITO_REGION=your-region
COGNITO_USER_POOL_ID=your-user-pool-id
COGNITO_CLIENT_ID=your-public-app-client-id
```

### User Service

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/ecommerce_user_db
COGNITO_REGION=your-region
COGNITO_USER_POOL_ID=your-user-pool-id
COGNITO_CLIENT_ID=your-public-app-client-id
```

### Order Service

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/ecommerce_order_db
COGNITO_REGION=your-region
COGNITO_USER_POOL_ID=your-user-pool-id
COGNITO_CLIENT_ID=your-public-app-client-id
INTERNAL_SERVICE_TOKEN=server-only-placeholder

USER_SERVICE_URL=http://localhost:5002
PRODUCT_SERVICE_URL=http://localhost:5001
```

> Never commit real passwords, tokens, or Cognito values to GitHub.

---

## ▶️ Running the Application

Start each service in a separate terminal.

### Product Service

```bash
cd product_services
python app.py
```

Runs on:

```text
http://localhost:5001
```

### User Service

```bash
cd user_services
python app.py
```

Runs on:

```text
http://localhost:5002
```

### Order Service

```bash
cd order_service
python app.py
```

Runs on:

```text
http://localhost:5003
```

### API Gateway

```bash
cd api_gateway
python app.py
```

Runs on:

```text
http://localhost:5000
```

### Frontend

```bash
cd front_end
python app.py
```

Runs on:

```text
http://localhost:5500
```

---

# 🔌 API Endpoints

## Users

### Create User

```http
POST /users
```

Example request:

```json
{
    "name": "Raj",
    "email": "raj@gmail.com"
}
```

### Get Users

```http
GET /users
```

### Get User

```http
GET /users/{id}
```

---

## Products

### Create Product

```http
POST /products
```

Example:

```json
{
    "name": "Laptop",
    "price": 55000,
    "stock": 10
}
```

### Get Products

```http
GET /products
```

### Get Product

```http
GET /products/{id}
```

### Update Stock

```http
PUT /products/{id}/stock
```

Example:

```json
{
    "stock": 20
}
```

### Delete Product

```http
DELETE /products/{id}
```

---

## Orders

### Create Order

```http
POST /orders
```

Example:

```json
{
    "user_id": 1,
    "product_id": 1,
    "quantity": 2
}
```

### Get Orders

```http
GET /orders
```

### Get Order

```http
GET /orders/{id}
```

---

# 🧪 Example API Flow

### 1. Create User

```text
POST /users
```

```json
{
    "name": "Raj",
    "email": "raj@gmail.com"
}
```

User ID:

```text
1
```

### 2. Create Product

```text
POST /products
```

```json
{
    "name": "Laptop",
    "price": 55000,
    "stock": 10
}
```

Product ID:

```text
1
```

### 3. Create Order

```text
POST /orders
```

```json
{
    "user_id": 1,
    "product_id": 1,
    "quantity": 2
}
```

The system:

1. Checks whether the user exists.
2. Checks whether the product exists.
3. Checks product stock.
4. Calculates total price.
5. Reduces product stock.
6. Creates the order.
7. Stores the order in PostgreSQL.

Example:

```text
Product price = ₹55,000
Quantity      = 2

Total         = ₹110,000
```

Stock:

```text
Before order = 10
Quantity     = 2
After order  = 8
```

---

# 🌐 Frontend

The frontend dashboard is available at:

```text
http://localhost:5500
```

It displays:

* Users
* Products
* Product stock
* Orders
* Order quantity
* Order total
* Order status

---

# 🔒 Security

Protected API requests use a verified Cognito access token. The browser never receives the server-only `INTERNAL_SERVICE_TOKEN`.

---

# 📊 Example Result

```text
E-Commerce Dashboard

Users
-------------------------
Raj
ID: 1
Email: raj@gmail.com

Products
-------------------------
Laptop
Price: ₹55,000
Stock: 8

Orders
-------------------------
Order #1
User ID: 1
Product ID: 1
Quantity: 2
Total: ₹110,000
Status: CONFIRMED
```

---

# 🚀 Future Improvements

* Docker and Docker Compose
* JWT authentication
* Redis caching
* RabbitMQ/Kafka messaging
* API documentation with Swagger/OpenAPI
* Unit and integration tests
* CI/CD with GitHub Actions
* Centralized logging
* Monitoring and health checks
* Kubernetes deployment
* Payment service
* Inventory service
* Notification service

## Authentication

The browser uses an Amazon Cognito User Pool public App Client with OAuth 2.0 Authorization Code Flow and PKCE. Cognito Managed Login collects and verifies the user's email, given name, and family name according to the User Pool attribute settings. The app stores the short-lived access token in `sessionStorage`; it does not use an ID token or refresh token as API authorization, and it never contains a client secret.

The frontend reads these placeholders from its environment:

```env
COGNITO_DOMAIN=https://your-domain.auth.your-region.amazoncognito.com
COGNITO_CLIENT_ID=your-public-app-client-id
COGNITO_REDIRECT_URI=http://localhost:5500/
COGNITO_LOGOUT_URI=http://localhost:5500/
COGNITO_SCOPES=openid email profile
```

The API Gateway, user service, order service, and product service validate access-token signatures using the Cognito JWKS endpoint. They check the issuer, expiration, `RS256`, `token_use=access`, `sub`, and the expected `client_id`. JWKS keys are cached in memory. The user service then calls Cognito UserInfo with that already-validated access token and uses the returned `email`, `given_name`, and `family_name` claims for profile synchronization.

`GET /users/me` maps the verified Cognito `sub` to `users.cognito_sub`, synchronizing the email, given name, and family name profile on first access. It reports the identity provider as Amazon Cognito only after the verified UserInfo lookup succeeds. The `cognito_sub` column is nullable so existing users are preserved. The order service derives `orders.user_id` from this mapping, filters `GET /orders` to that user, and returns 404 for another user's order. A conflicting body `user_id` on `POST /orders` is rejected.

### AWS Cognito configuration required after this code change

Create a User Pool, a public App Client with no client secret, a hosted UI domain, and callback/logout URLs matching the configured values. Enable email sign-up and verification. Add `email`, `given_name`, and `family_name` as required or writable standard attributes according to your registration policy. Allow the `openid`, `email`, and `profile` scopes so Cognito UserInfo can return the profile. Then provide these values to Compose as placeholders replaced by your deployment configuration:

```env
COGNITO_REGION=your-region
COGNITO_USER_POOL_ID=your-user-pool-id
COGNITO_CLIENT_ID=your-public-app-client-id
COGNITO_ISSUER=https://cognito-idp.your-region.amazonaws.com/your-user-pool-id
COGNITO_DOMAIN=https://your-domain.auth.your-region.amazoncognito.com
COGNITO_REDIRECT_URI=https://your-frontend-host/
COGNITO_LOGOUT_URI=https://your-frontend-host/
COGNITO_SCOPES=openid email profile
INTERNAL_SERVICE_TOKEN=server-only-internal-placeholder
```

### Verified production OAuth issue

The deployed HTTPS flow was tested against the configured Cognito domain and returned:

```text
error=invalid_request
error_description=invalid_scope
```

The application is requesting `openid email profile`, but the Cognito App Client currently does not allow the requested scope, or the deployed `COGNITO_SCOPES` value does not match the App Client. In the Cognito console, open the App Client, enable the authorization-code grant with PKCE, add the `openid`, `email`, and `profile` scopes to the allowed scopes, and save. The `profile` scope is required for UserInfo to return `given_name` and `family_name`.

### Database migration

On startup, the user service runs an additive PostgreSQL migration equivalent to:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS cognito_sub VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS family_name VARCHAR(100);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_cognito_sub
ON users (cognito_sub) WHERE cognito_sub IS NOT NULL;
```

It does not drop tables, delete users, or wipe existing data.

---

# 👨‍💻 Author

**Raj**

Python | Flask | PostgreSQL | REST API | Microservices

---

## 📄 License

This project is created for learning and portfolio purposes.

