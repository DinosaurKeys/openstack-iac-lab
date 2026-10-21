"""Small database-backed Flask exercise, served by Gunicorn."""
import os

import psycopg2
from flask import Flask, jsonify

app = Flask(__name__)


def connect():
    return psycopg2.connect(
        host=os.environ['DB_HOST'], dbname='labapp', user='labapp',
        password=os.environ['DB_PASSWORD'], connect_timeout=3,
    )


@app.get('/health')
def health():
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
        return jsonify(status='ok')
    except psycopg2.Error:
        app.logger.exception('Database health check failed')
        return jsonify(status='database unavailable'), 503


@app.get('/visits')
def count_visits():
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM visits')
        count = cur.fetchone()[0]
    return jsonify(visits=count)


@app.post('/visits')
def add_visit():
    with connect() as conn, conn.cursor() as cur:
        cur.execute('INSERT INTO visits DEFAULT VALUES RETURNING id')
        visit_id = cur.fetchone()[0]
    return jsonify(id=visit_id), 201


@app.get('/')
def index():
    return jsonify(app='OpenStack IaC Lab', health='/health', counter='/visits')
