# InOrbit Edge SDK demo

Code for generating synthetic data for simulating a fleet of robots. It uses the InOrbit Edge SDK for publishing robot data to InOrbit. It also uses the InOrbit API for publishing map data (see `map.png` file).

## How to use

Export required environment variables and execute the `demo.py` script. Use the `virtualenv` used on the `CONTRIBUTING.md` guide.

```bash
export INORBIT_URL="https://control.inorbit.ai"
export INORBIT_API_URL="https://api.inorbit.ai"
export INORBIT_API_KEY="foobar123"
# Disable SSL for local development only
export INORBIT_USE_SSL="true"

python example.py
```
