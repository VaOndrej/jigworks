# demo/

Demo projects built by Jigworks workflow runs (`feature-development` 1.6.0 and later). Point a
run here with `jigworks.repoPath: "demo"` in VS Code (or `jigworks run --repo demo`): the agents
may then change only files under this folder, and the gate runs the tests it finds here (or
the commands named in `demo/.jigworks/gate.toml`).

Each demo lives in its own subfolder with its own README, tests and start command.
