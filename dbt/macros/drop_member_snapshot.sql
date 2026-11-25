{#- Drops the member snapshot table so it can be replayed from the first coverage year. -#}
{% macro drop_member_snapshot() %}
    {% set relation = adapter.get_relation(
        database=target.database,
        schema='snapshots',
        identifier='snap_member_coverage'
    ) %}
    {% if relation %}
        {% do adapter.drop_relation(relation) %}
        {{ log("Dropped " ~ relation, info=true) }}
    {% else %}
        {{ log("No snapshot table to drop", info=true) }}
    {% endif %}
{% endmacro %}
