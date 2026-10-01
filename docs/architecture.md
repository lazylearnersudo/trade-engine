# Architecture

## Objective

Trade Engine is a modular trading platform. Phase 1 focuses on execution management, broker integration, application state, and risk controls. Backtesting and historical market-data management are later concerns.

## Composition

The top-level application is deliberately thin. It composes module UIs and provides shared application concerns. Business capabilities remain inside modules.

A module owns its behavior and may expose a UI, service/API, or both. A module should not contain layers it does not need.

## Runtime modes

### Local

The complete application must be runnable without cloud infrastructure or live broker accounts. Local substitutes/adapters provide required infrastructure and broker behavior.

### Deployed

The deployed topology may use Vercel for the web application, Oracle Cloud for continuously running services, and Supabase for application data. Exact technology and deployment choices are finalized separately.

Supabase application storage is not a market-data store.

## Broker boundary

Broker-specific APIs sit behind a common broker boundary. A dummy broker is a first-class implementation for development and automated testing. Live broker integrations must not leak broker-specific behavior into unrelated business modules.

## UI

The application shell owns navigation, shared layout, session/auth integration, notifications, and light/dark/system theme behavior. Module UIs use shared visual primitives and tokens.

## Testing

Tests are part of module ownership. Behavioral changes should be represented by tests where practical. Integration tests protect contracts between modules/adapters, and regression tests protect previously fixed failures.

## Future backtesting

Backtesting is intentionally separated from Phase 1. Historical data may be sourced from external providers and stored independently from the primary application database. This concern must not complicate the initial execution platform.
