# Phase 5 — Motion and audio

## Inputs and dependencies

Presentation components; browser Web Audio, IntersectionObserver, CSS animations, and Web Animations API. No music service or gallery track is required.

## Tasks and outputs

- Add short section reveals, command progress/cursor illustration, gallery filter transitions, and focus/hover feedback.
- Disable decorative motion for reduced-motion preference, including changes made during a visit.
- Compose an original four-chord ambient texture procedurally with sine harmonics, gentle envelopes, and a quiet copy-feedback cue.
- Start audio only through the sound button; remember preference/volume without bypassing the next visit’s user gesture.
- Fade ambient music out while deliberate gallery playback runs; pause on hidden pages; close audio resources when leaving.
- Keep install/about/changelog/docs silent. Presentation/showcase pages offer the opt-in soundtrack.

## Commands

`npm run check`, `npm run test:browser`.

## Acceptance

Fresh visitors hear nothing. Enabled sound can be muted, volume can reach zero, and media does not overlap with other media. Hidden tabs do not keep producing ambient sound. No information depends on sound or animation. Browser rejection of audio does not break navigation or gallery use.

## Completion notes

The soundtrack is original code-generated audio, not a downloaded song. Native video/audio controls manage sample volume independently from ambient volume.
