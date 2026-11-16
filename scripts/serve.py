"""Loopback service entry point with JSON scoring logs enabled."""

import logging

import uvicorn

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run("scalping_gold.service:app", host="127.0.0.1", port=8000, log_level="info")
