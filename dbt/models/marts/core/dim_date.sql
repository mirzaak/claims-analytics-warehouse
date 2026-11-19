-- Grain: one row per calendar day from 2007-01-01 to 2011-12-31, plus an unknown row
-- (date_key -1) for facts with a missing service date.

with days as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2007-01-01' as date)",
        end_date="cast('2012-01-01' as date)"
    ) }}
),

calendar as (
    select
        {{ date_key('date_day') }} as date_key,
        cast(date_day as date) as full_date,
        cast(extract(year from date_day) as {{ dbt.type_int() }}) as calendar_year,
        cast(extract(quarter from date_day) as {{ dbt.type_int() }}) as calendar_quarter,
        cast(extract(month from date_day) as {{ dbt.type_int() }}) as month_number,
        {{ year_month('date_day') }} as year_month
    from days
),

final as (
    select
        date_key,
        full_date,
        calendar_year,
        calendar_quarter,
        month_number,
        case month_number
            {%- for name in ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                             'August', 'September', 'October', 'November', 'December'] %}
            when {{ loop.index }} then '{{ name }}'
            {%- endfor %}
        end as month_name,
        year_month,
        {{ date_from_parts('calendar_year', 'month_number', 1) }} as month_start_date
    from calendar
)

select * from final
union all
select
    -1 as date_key,
    cast(null as date) as full_date,
    cast(null as {{ dbt.type_int() }}) as calendar_year,
    cast(null as {{ dbt.type_int() }}) as calendar_quarter,
    cast(null as {{ dbt.type_int() }}) as month_number,
    'Unknown' as month_name,
    cast(null as {{ dbt.type_int() }}) as year_month,
    cast(null as date) as month_start_date
