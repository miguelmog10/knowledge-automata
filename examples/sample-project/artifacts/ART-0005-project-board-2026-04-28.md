# Tallyleaf greenhouse inventory app: project board meeting

Date: 28 April 2026
Present: Julie Tremblay (product owner, chair), Marc Gagnon (tech lead), Aisha Benali (UX designer), Paul Nguyen (pilot grower advisor), Sofia Ramos (contract developer)

## 1. Pilot feedback

The count screen has been in use at Paul’s greenhouse for three weeks. Growers liked the
large buttons, but the status ladder did not fit how they work. Rooted cuttings arrive
from a supplier already growing, and finished plants bought for resale arrive ready to
sell. Growers had to tap through statuses that never happened, and Paul found 41 batches
with the wrong status after the first two weeks.

Decision: the board replaced the single status ladder with one status path per crop type.
Seed-grown crops keep the full ladder, rooted cuttings start at growing, and bought-in
finished plants start at ready. Discarded stays available at any step.

## 2. Bench labels

Paul’s printed QR codes are still readable after three weeks of watering. No decision
yet: Aisha will design a label layout before the May meeting.

## Actions

- Aisha: redesign the status picker so it shows only the steps for each crop type.
- Marc: add a crop type field to the batch table and migrate the existing batches.
