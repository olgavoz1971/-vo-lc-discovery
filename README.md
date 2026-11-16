# vo-lc-discovery

Discover **lightcurve routes** in the Virtual Observatory.

A caller (a person, a web application, or an AI agent) gives a sky region, a time interval, and a rough spectral position. The package is meant to return:

- endpoints that probably hold matching lightcurves, each with a flag for how sure we are;
- on request, the provider’s own response for one chosen route.

We are **at the very beginning**. Work so far is registry-side: listing SSA and TAP candidates and classifying them from registry text. There is no stable public API yet.

See `docs/vo-lightcurve-discovery-design.md` for the intended design.

## License

MIT
