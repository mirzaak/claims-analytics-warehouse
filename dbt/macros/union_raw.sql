{#-
  Union one raw table per loaded CMS sample, adding the sample number.
  table_template uses {sample}, for example 'beneficiary_2008_s{sample}'.
-#}
{% macro union_raw(table_template, extra_columns={}) -%}
    {%- for sample in var('synpuf_samples') %}
    select
        *,
        {{ sample }} as synpuf_sample
        {%- for name, value in extra_columns.items() %},
        {{ value }} as {{ name }}
        {%- endfor %}
    from {{ source('synpuf', table_template.replace('{sample}', '%02d' % sample)) }}
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}
{%- endmacro %}
