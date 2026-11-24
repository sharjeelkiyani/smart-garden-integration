# Smart Garden for Home Assistant

Brings a **Smart Garden** irrigation controller into Home Assistant: every zone as a switch, soil
moisture, watering today, time left, next run, rain and relay-board status, plus **Stop all**,
**Run schedule** buttons and a **Water zone** action for automations. The Smart Garden app stays in
charge of safety - one zone at a time, each zone's time limit, valves checked off - so Home Assistant
can't over-water even if an automation goes wrong.

Works with any Home Assistant install (Container, Core, OS). On Home Assistant OS you can instead use
the [Smart Garden app](https://github.com/sharjeelkiyani/smart-garden-ha), which runs the controller
itself inside Home Assistant.

## Install

**Home Assistant 2026.11 or newer (Marketplace)**
1. **Marketplace → Add from a GitHub link** → `sharjeelkiyani/smart-garden-integration` → **Add**, then
   install **Smart Garden**.
2. Restart Home Assistant.

**Older versions with HACS:** HACS → ⋮ → Custom repositories → this repository, type *Integration*.

**By hand:** copy `custom_components/smart_garden` into your `config/custom_components/` and restart.

## Set up
1. In Smart Garden open **My account → Connection keys**, enter your password and **Make a connection
   key**. Copy it - it's shown once.
2. In Home Assistant: **Settings → Devices & services → Add integration → Smart Garden**.
3. Enter the address you open Smart Garden at (for example `http://192.168.1.50:5120`) and the key.

The key acts as the Smart Garden account that made it:
- **user** account - see everything, water, stop, run schedules;
- **admin** account - also turn zones and automatic watering on or off.

Revoke the key in Smart Garden at any time; Home Assistant then asks for a new one. Moved the garden to
a new address? **Settings → Devices & services → Smart Garden → ⋮ → Reconfigure**.

## What you get

| Device | Entities |
|---|---|
| Garden | Watering now, Time left, Next run, Water today, Raining, Relay boards, garden sensors (soil, temperature, humidity, rain, alarm), Stop all, Run *schedule*, Automatic watering (admin) |
| Each zone | Water (on = water for the zone's usual minutes, off = stop), Soil moisture, Watered today, Time left, Zone on (admin) |

**Action `smart_garden.water`** - target a zone's *Water* switch:

```yaml
action: smart_garden.water
target:
  entity_id: switch.front_lawn_water
data:
  minutes: 5            # or: until_soil: true  (needs a soil sensor on the zone)
```

If another zone is watering, the new one waits its turn.

## Sidebar
The integration adds a **Smart Garden** item to the sidebar that opens the full app (turn it off in the
integration's **Configure** options). Browsers only keep you signed in inside Home Assistant when the two
are on the *same site*: the same IP on different ports (e.g. HA `http://192.168.1.10:8123`, garden
`http://192.168.1.10:5120` through a proxy), or names under the same domain over HTTPS. Otherwise the
page asks you to sign in each time - open it in its own tab instead.

## Privacy
Everything stays on your network: Home Assistant talks only to your Smart Garden, every 10 seconds,
with the key you gave it. Nothing is sent anywhere else.

## Problems
Open an issue: https://github.com/sharjeelkiyani/smart-garden-integration/issues
