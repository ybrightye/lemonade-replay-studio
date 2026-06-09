# Demo Footage

The public example is documented in `examples/dark-souls/`.

The current demo run uses a local slice of this Wikimedia Commons file:

https://commons.wikimedia.org/wiki/File:TJ_Miller_and_Kumail_Nanjiani_play_Dark_Souls_III_(extended).webm

License shown on Wikimedia Commons:

- Creative Commons Attribution 3.0 Unported
- Author/source attribution: Bandai Namco Entertainment America

Local development files:

- `tj_kumail_dark_souls_480p.webm`: downloaded source file
- `tj_kumail_dark_souls_20min.mp4`: local 20-minute demo slice

The latest demo run can be generated with:

```bash
scripts/run_dark_souls_demo.sh \
  ../../work/test-media/dark-souls/tj_kumail_dark_souls_20min.mp4 \
  demo-runs/dark-souls-example
```

Use demo footage with attribution preserved.
