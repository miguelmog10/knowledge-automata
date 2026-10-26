# Tallyleaf greenhouse inventory app: project board meeting

Date: 3 February 2026
Present: Julie Tremblay (product owner, chair), Marc Gagnon (tech lead), Aisha Benali (UX designer), Paul Nguyen (pilot grower advisor)

## 1. Mobile platform

Marc compared building two native apps (Swift for iOS and Kotlin for Android) with one
Flutter app. Native apps would give the most direct access to the camera and offline
storage, but the team has two developers, and growers use both iPhones and Android
phones on the greenhouse floor.

Decision: the board chose to build one Flutter app for iOS and Android, because a single
codebase lets two developers ship the walkthrough count to both platforms at the same
time. Separate native apps were rejected for version 1.

## 2. Bench labels

Paul suggested printing QR codes for every bench, so that a count could start with a
scan. No decision yet: Aisha will ask the two pilot growers how they label benches today
and report back at the March meeting.

## 3. Risks

Marc warned that two workers counting the same bench while offline could create
conflicting counts when their phones sync. If that happens, a grower could see the wrong
quantity for a batch until someone recounts it.

## Actions

- Marc: build a Flutter prototype of the count screen with large plus and minus buttons by 20 February.
- Aisha: test the prototype in direct sunlight, with work gloves, at Paul’s greenhouse.
