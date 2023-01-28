# coding: utf-8
from itertools import groupby
from sanic import Blueprint
from app.handler.base import login_required
from app.sqlrest.query import Query
from app.handler.base import success, error, hash_md5, encode_token
from app import config

router = Blueprint("index")

# 查所有表结构
@router.route("/api/tables")
async def get_tables(request):
    db = request.app.db
    database = config.get("database.db")
    table_list = await db.query(f"SELECT table_name FROM information_schema.tables WHERE table_schema='{database}'")
    tables = {}
    for i in table_list:
        table = i['table_name']
        table_info = await db.query(f"SELECT column_name name,data_type type,column_comment comment,column_default value FROM information_schema.columns WHERE table_name='{table}'")
        tables[table] = table_info
    return success(tables)

# get方法查询函数
@router.route("/api/<table>", methods=["GET"])
@login_required
async def query(request, table):
    db = request.app.db
    result = {}
    query_string = request.query_string
    query = Query(table, query_string)

    sql = query.to_sql()
    # 1.主表查询
    data = await db.query(sql)
    # 根据field定义，做数据处理
    data = query.data_convert(query.fields, data)
    # 2.统计查询
    info = await db.get(query.to_count_sql())
    result['meta'] = {"total": info['cnt']}
    # 3.子表查询
    for relation in query.relation:
        # master表外键所有id
        idhub = set([str(i[relation.master_key]) for i in data])
        if len(idhub) == 0:
            continue
        ids = ",".join([ f"'{i}'" for i in idhub])
        # 查子表数据
        sql = relation.to_sql() + f" WHERE {relation.relate_key} IN ({ids})"
        print("SUBQUERY SQL>>>", sql)
        relation_data = await db.query(sql)
        query.data_convert(relation.fields, relation_data)
        # 合并数据
        relation.merge_table_data(data, relation_data)

    result['list'] = data
    return success(result)

# POST,PUT方法，插入和更新数据，有查询条件触发更新
@router.route("/api/<table>", methods=["POST", "PUT"])
@login_required
async def post(request, table):
    db = request.app.db
    query_string = request.query_string
    data = request.json
    if not data:
        return error("ERROR: data is null")
    # 有query触发更新
    query = Query(table, query_string)
    if query_string:
        sql = query.to_update_sql(data)
    else:
        sql = query.to_insert_sql(data)
    result = await db.execute(sql)
    return success(result)

# delete data
@router.route("/api/<table>", methods=["DELETE"])
@login_required
async def delete(request, table):
    db = request.app.db
    query_string = request.query_string
    # 有query触发更新
    query = Query(table, query_string)
    if query_string:
        result = await db.execute(query.to_delete_sql())
        return success(result)
    else:
        return error("ERROR: No query string")
