# Itonami Zuhyo（図表）

Zuhyo is the planned Itonami presentation dapp. Its model and UI are intended
to be written in Kotoba and built by Amu selfhost for the user's browser and
Itonami OS. Browser execution targets Wasm; QEMU is used to qualify the OS
host. The deck editor, presentation mode and durable storage are not yet
implemented or released.

The [shared office dapps design](https://github.com/cloud-itonami/app-itonami-bunsho/blob/2fd57da398b9e3ae7e817994a190b1c9f860dc38/docs/office-dapps-spec.md)
covers the app/host boundary, state and migration, consent, and release gates.
The link is pinned to the design proposal in the open Bunsho draft PR;
[JUN-705](https://linear.app/kotobalabs/issue/JUN-705) tracks Zuhyo.

The existing CLJS appview is a placeholder, not the planned presentation editor.
The candidate `zuhyo.itonami.app` is not a claim of an available or deployed
service.
