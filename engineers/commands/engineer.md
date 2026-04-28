# /engineer

Dispatch a single bounded request to the engineer subagent.

## Usage

```
/engineer <verb> <json-args>
```

`<verb>` must be one of: `run-python`, `run-cpp`, `run-matlab`, `web-search`, `index-source`, `count-tokens`, `compute`.

`<json-args>` is a single JSON object matching the verb's input schema (see `engineers/agents/engineer.md`).

## Examples

```
/engineer run-python {"code":"print(2+2)","timeout_s":5}
/engineer web-search {"query":"Bolzano-Weierstrass proof variants","k":5}
/engineer index-source {"path":"papers/source/foo.pdf","kind":"pdf"}
/engineer compute {"lang":"python","script":"import sympy; print(sympy.simplify('x**2 - x*x'))","env_pkgs":["sympy"],"timeout_s":15}
```

## Instructions

Read the argument after this command. Split it into `<verb>` (first whitespace-delimited token) and `<json-args>` (the rest, verbatim).

Validate locally before delegating:
- The verb is in the allowed set above. If not, print the list and stop.
- The args parse as JSON. If not, print the parse error and stop.

Delegate to the `engineer` subagent. Pass it a single message:

> `<verb> <json-args>`

The engineer will run the audit harness, execute the verb, and return a compact JSON report. Print the report verbatim — do not summarize, do not interpret.

If the engineer refuses (e.g., sandbox violation, malformed args), print its one-line refusal and stop.

$ARGUMENTS
