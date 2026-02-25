# 5980 Key-Value Store

## Prerequisites

- Python 3.13
- Pipenv (recommended)


## Setup From Git Clone

```powershell
git clone https://github.com/alber791/5980-Key-Value.git
cd 5980-Key-Value
```

Install dependencies and create the virtual environment:

```powershell
pipenv install
```

## Start the Server

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

## Demo
https://github.com/user-attachments/assets/2c8134db-b4bf-4ee0-afd9-4156cc61e78a

