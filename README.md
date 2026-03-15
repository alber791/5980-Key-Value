# 5980 Key-Value Store

## Prerequisites

- Python 3.13
- Docker Desktop on Windows, or Docker Engine on Linux
- Pipenv (recommended)


## Setup From Git Clone

```powershell
git clone https://github.com/alber791/5980-Key-Value.git
cd 5980-Key-Value
```

## Build and Run Container

Build the container

```
docker build -t kv-store .
```

Run the container

```
docker run -p 8080:8080 kv-store
```

## Start the Server Locally (Without container)

Install dependencies and create the virtual environment:

```powershell
pipenv install
```

Run the API with Uvicorn:

```powershell
pipenv run uvicorn app:app --host 127.0.0.1 --port 8080 --reload
```

Server URL:

- API base: `http://127.0.0.1:8080`

## API Endpoints

- `GET /{key}`
- `PUT /{key}` with JSON body: `{ "value": <any JSON value> }`
- `DELETE /{key}`

## Data and Logs

- Data is persisted to `kv_store.json`
- Logs are written to `kv_operations.log`

## Demo with container
https://github.com/user-attachments/assets/5015d830-f205-48d5-b9a9-f822b4e58fd5

