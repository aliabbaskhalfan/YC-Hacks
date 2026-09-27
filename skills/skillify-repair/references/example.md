# Example

Input transcript:

> Swapped the front right knee actuator, old one was lot B and scorching.
> Recalibrated, ran a stand cycle, holding fine.

Robot context says the front-right knee actuator lost torque under load. The
current actuator-removal SOP does not mention supplier lots.

Expected extraction preserves this order: swap actuator, recalibrate, run stand
cycle. It records `supplier_lot: B`, attributes the hot old actuator as the
technician's root-cause observation, and captures the stand cycle as verification.
The hygiene label is `addition` because the supplier-lot check is new field
knowledge. The note retains the original transcript and its incident provenance.
