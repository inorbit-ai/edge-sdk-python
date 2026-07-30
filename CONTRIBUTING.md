# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

## Get Started

Ready to contribute? Here's how to set up `edge-sdk-python` for local development.

1. Fork the `edge-sdk-python` repo on GitHub.

2. Clone your fork locally:

    ```bash
    git clone git@github.com:{your_name_here}/edge-sdk-python.git
    ```

3. Install the project in editable mode. (It is also recommended to work in a virtualenv or anaconda environment):

    ```bash
    cd edge-sdk-python/
    virtualenv venv
    . venv/bin/activate
    pip install -e .[dev]
    ```

4. Create a branch for local development:

    ```bash
    git checkout -b {your_development_type}/short-description
    ```

   Ex: feature/read-tiff-files or bugfix/handle-file-not-found<br>
   Now you can make your changes locally.

5. When you're done making changes, check that your changes pass linting and
   tests, including testing other Python versions with make:

    ```bash
    make build
    ```

6. Commit your changes and push your branch to GitHub:

    ```bash
    git add .
    git commit -m "Resolves gh-###. Your detailed description of your changes."
    git push origin {your_development_type}/short-description
    ```

7. Submit a pull request through the GitHub website.

## Deploying

A reminder for the maintainers on how to deploy.
Make sure you are on the `main` branch and have pulled the latest changes.

Setup `virtualenv` with `dev` requirements:

```bash
cd edge-sdk-python/
virtualenv venv
. venv/bin/activate
pip install -e .[dev]
```

Then run `bump2version` on a branch and choose the part of the version to be
bumped. Pass `--no-tag`: CI tags the release itself, on the commit that actually
publishes (see below).

```bash
git checkout -b bump-version-x.y.z
bump2version --no-tag patch # possible: major / minor / patch
git push -u origin bump-version-x.y.z
```

Open a pull request for it and **keep `Bump version` in the merge commit
message**: the publish job triggers on
`contains(github.event.head_commit.message, 'Bump version')`, and a squash merge
takes the PR title, so leave the title as `bump2version` wrote it (`Bump version:
x.y.z → a.b.c`).

Merging publishes the package to PyPI, then creates the `vA.B.C` tag and a
GitHub release from the published version.

Why `--no-tag`: `bump2version` tags the commit it creates, which is only correct
when the bump goes straight to `main`. Merge commits are disabled on this repo,
so a bump arriving through a PR is squashed or rebased into a *different* commit
and that tag would point at something never reachable from `main` — which is how
`v3.0.0` came to dangle and `v3.1.0` was never tagged at all. Bumping directly on
`main` still works if you prefer it (`bump2version patch`, then `git push && git
push --tags`); the CI step skips tagging when the release already exists.
