# Not a result

Testbed dry run 1 (2026-11-27 15:32 UTC): the relay process exited on an unhandled 429 from the public Devnet RPC during the first job's final verdict; every later job failed with a broken pipe. Fixed in relay.ts (unhandled rejections logged, slower throttle) and testbed_demo.py (relay restart). Actor SOL swept back (0.879 SOL). Kept for the record only.
