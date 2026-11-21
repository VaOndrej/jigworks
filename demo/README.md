# demo/

Demo projects built by Jigworks workflow runs (`feature-development` 1.6.0 and later). Point a
run here with `jigworks.repoPath: "demo"` in VS Code (or `jigworks run --repo demo`): the agents
may then change only files under this folder, and the gate runs the tests it finds here (or
the commands named in `demo/.jigworks/gate.toml`).

Each demo lives in its own subfolder with its own README, tests and start command.

| Demo | What it is | Run it |
|---|---|---|
| [`btc-paper-trader/`](btc-paper-trader/README.md) | Local BTC/USD paper-trading exchange with an order book, 1,000 bots and a browser UI | `cd demo && uv sync && uv run btc-paper-trader --bots 1000` |
