-- Two versions of the same member must never cover the same date.
-- Overlaps would make the point-in-time join return two rows and double-count facts.

select
    earlier.member_id,
    earlier.synpuf_sample,
    earlier.valid_from as earlier_valid_from,
    earlier.valid_to as earlier_valid_to,
    later.valid_from as later_valid_from
from {{ ref('dim_member') }} as earlier
inner join {{ ref('dim_member') }} as later
    on earlier.member_id = later.member_id
    and earlier.synpuf_sample = later.synpuf_sample
    and earlier.valid_from < later.valid_from
    and later.valid_from <= earlier.valid_to
