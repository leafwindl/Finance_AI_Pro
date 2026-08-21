#!/usr/bin/env python3

"""
数据库连接与路由模块 — db_conn.py (v2.0)
=============================================
提供三数据库连接管理 + kb_code -> schema/index 路由。

新增能力（v2.0）:
    1. route_pg_schema(kb_code)  - 查 sys_config.kb_registry 自动路由
    2. route_es_index(kb_code)   - 自动构造 knowledge_chunks_{kb_code_lower}
    3. list_all_es_indexes()     - 跨知识库检索时用
    4. health_check_all()        - 三库连接状态 + kb 缓存信息

使用方式:
    from db_conn import get_pg_conn, get_es_client, get_neo4j_driver
    from db_conn import route_pg_schema, route_es_index

    schema  = route_pg_schema("KB01")     # -> "kb01_business"
    es_idx  = route_es_index("KB01")       # -> "knowledge_chunks_kb01"
"""

import os
import logging
from pathlib import Path
from typing import Optional

import psycopg2
from elasticsearch import Elasticsearch
from neo4j import GraphDatabase

_project_root = Path(__file__).resolve().parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

logger = logging.getLogger(__name__)

POSTGRES_CONFIG = {
    "host":     os.getenv("PG_HOST", os.getenv("POSTGRES_HOST", "localhost")),
    "port":     int(os.getenv("PG_PORT", os.getenv("POSTGRES_PORT", "5432"))),
    "user":     os.getenv("PG_USER", os.getenv("POSTGRES_USER", "postgres")),
    "password": os.getenv("PG_PASSWORD", os.getenv("POSTGRES_PASSWORD", "")),
    "dbname":   os.getenv("PG_DBNAME", os.getenv("POSTGRES_DB", "knowledge_base")),
}

_es_url = os.getenv("ES_HOST", "http://localhost:9200")
_es_url_without_scheme = _es_url.split("://", 1)[-1]
_es_host, _, _es_port = _es_url_without_scheme.partition(":")
ELASTICSEARCH_CONFIG = {
    "host": os.getenv("ELASTICSEARCH_HOST", _es_host),
    "port": int(os.getenv("ELASTICSEARCH_PORT", _es_port or "9200")),
}

_neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_CONFIG = {
    "uri":      _neo4j_uri,
    "user":     os.getenv("NEO4J_USER", "neo4j"),
    "password": os.getenv("NEO4J_PASSWORD", "password"),
}

ES_INDEX_PREFIX = os.getenv("ES_INDEX_PREFIX", "knowledge_chunks")
DEFAULT_PG_SCHEMA = os.getenv("DEFAULT_PG_SCHEMA", "public")

_pg_connection: Optional["psycopg2.extensions.connection"] = None
_es_client: Optional[Elasticsearch] = None
_neo4j_driver: Optional[GraphDatabase.driver] = None


def get_pg_conn() -> "psycopg2.extensions.connection":
    global _pg_connection
    if _pg_connection is None or _pg_connection.closed:
        try:
            _pg_connection = psycopg2.connect(**POSTGRES_CONFIG)
            # 检索服务只读，用 autocommit 避免长时间挂起事务占锁，
            # 否则会阻塞 rebuild 等 DDL（DROP TABLE 等锁超时）。
            _pg_connection.autocommit = True
            logger.info("PostgreSQL connected: %s:%s/%s", POSTGRES_CONFIG["host"], POSTGRES_CONFIG["port"], POSTGRES_CONFIG["dbname"])
        except psycopg2.Error as e:
            logger.error("PostgreSQL connection failed: %s", e)
            raise
    return _pg_connection


def pg_health_check() -> bool:
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        return True
    except Exception:
        return False


def close_pg_conn() -> None:
    global _pg_connection
    if _pg_connection and not _pg_connection.closed:
        _pg_connection.close()
    _pg_connection = None


def get_es_client() -> Elasticsearch:
    global _es_client
    if _es_client is None:
        es_host = ELASTICSEARCH_CONFIG["host"]
        es_port = ELASTICSEARCH_CONFIG["port"]
        # 支持带安全认证的 ES 集群（空凭证时不带 basic_auth，兼容无认证部署）
        es_user = os.getenv("ES_USER", "")
        es_password = os.getenv("ES_PASSWORD", "")
        try:
            kwargs: dict = {"request_timeout": 30, "max_retries": 3}
            if es_user:
                kwargs["basic_auth"] = (es_user, es_password)
            _es_client = Elasticsearch(
                [f"http://{es_host}:{es_port}"],
                **kwargs,
            )
            if _es_client.ping():
                logger.info("Elasticsearch connected: %s:%s", es_host, es_port)
        except Exception as e:
            logger.error("Elasticsearch connection failed: %s", e)
            raise
    return _es_client


def es_health_check() -> bool:
    try:
        return get_es_client().ping()
    except Exception:
        return False


def close_es_client() -> None:
    global _es_client
    if _es_client is not None:
        _es_client.close()
    _es_client = None


def get_neo4j_driver() -> GraphDatabase.driver:
    global _neo4j_driver
    if _neo4j_driver is None:
        try:
            _neo4j_driver = GraphDatabase.driver(
                NEO4J_CONFIG["uri"],
                auth=(NEO4J_CONFIG["user"], NEO4J_CONFIG["password"]),
            )
            _neo4j_driver.verify_connectivity()
            logger.info("Neo4j connected: %s", NEO4J_CONFIG["uri"])
        except Exception as e:
            logger.error("Neo4j connection failed: %s", e)
            raise
    return _neo4j_driver


def neo4j_health_check() -> bool:
    try:
        get_neo4j_driver().verify_connectivity()
        return True
    except Exception:
        return False


def close_neo4j_driver() -> None:
    global _neo4j_driver
    if _neo4j_driver is not None:
        _neo4j_driver.close()
    _neo4j_driver = None


_schema_cache: dict[str, str] = {}
_index_cache: dict[str, str] = {}


def route_pg_schema(kb_code: Optional[str]) -> str:
    """根据 kb_code 路由到对应 PostgreSQL schema。"""
    if not kb_code:
        return DEFAULT_PG_SCHEMA
    if kb_code in _schema_cache:
        return _schema_cache[kb_code]
    _warm_schema_cache()
    if kb_code in _schema_cache:
        return _schema_cache[kb_code]
    prefix = kb_code.split("-")[0].strip()
    if prefix != kb_code and prefix in _schema_cache:
        _schema_cache[kb_code] = _schema_cache[prefix]
        return _schema_cache[prefix]
    schema_name = _query_schema(kb_code)
    if schema_name:
        _schema_cache[kb_code] = schema_name
        return schema_name
    if prefix != kb_code:
        schema_name = _query_schema(prefix)
        if schema_name:
            _schema_cache[kb_code] = schema_name
            _schema_cache[prefix] = schema_name
            return schema_name
    logger.warning("kb_code [%s] not registered, using default [%s]", kb_code, DEFAULT_PG_SCHEMA)
    _schema_cache[kb_code] = DEFAULT_PG_SCHEMA
    return DEFAULT_PG_SCHEMA


def route_es_index(kb_code: Optional[str]) -> str:
    """根据 kb_code 路由到对应 Elasticsearch 索引。"""
    if not kb_code:
        return ES_INDEX_PREFIX
    prefix = kb_code.split("-")[0].strip().lower()
    if prefix in _index_cache:
        return _index_cache[prefix]
    index_name = f"{ES_INDEX_PREFIX}_{prefix}"
    _index_cache[prefix] = index_name
    return index_name


def list_all_es_indexes() -> str:
    _warm_schema_cache()
    prefixes = set(k.split("-")[0].strip().lower() for k in _schema_cache)
    if not prefixes:
        return ES_INDEX_PREFIX
    return ",".join(sorted(f"{ES_INDEX_PREFIX}_{p}" for p in prefixes))


def list_all_pg_schemas() -> list[str]:
    _warm_schema_cache()
    return sorted(set(_schema_cache.values()))


def _query_schema(kb_code: str) -> Optional[str]:
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT schema_name FROM sys_config.kb_registry WHERE kb_code = %s AND is_active = TRUE",
            (kb_code,),
        )
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except Exception:
        return None


def _warm_schema_cache() -> None:
    global _schema_cache
    if _schema_cache:
        return
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute("SELECT kb_code, schema_name FROM sys_config.kb_registry WHERE is_active = TRUE")
        for kb_code, schema_name in cur.fetchall():
            _schema_cache[kb_code] = schema_name
        cur.close()
        if _schema_cache:
            logger.info("kb_registry cache warmed: %d KBs", len(_schema_cache))
    except Exception:
        pass


def close_all() -> None:
    close_pg_conn()
    close_es_client()
    close_neo4j_driver()


def health_check_all() -> dict:
    _warm_schema_cache()
    return {
        "postgres":      "healthy" if pg_health_check() else "unhealthy",
        "elasticsearch": "healthy" if es_health_check() else "unhealthy",
        "neo4j":         "healthy" if neo4j_health_check() else "unhealthy",
        "kb_count":      len(_schema_cache),
        "kb_codes":      sorted(_schema_cache.keys()),
    }
