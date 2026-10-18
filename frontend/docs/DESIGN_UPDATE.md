# Visual redesign — 17 October 2026

The user requested an Apple-inspired, more deliberate visual treatment while retaining the complete professional dashboard. The provided SONOTYPE brief was treated as design inspiration, not as a replacement product specification.

- Replaced the dense left sidebar and utility header with compact, sticky top navigation and a separate simulation control bar.
- Established a system-font hierarchy, larger headings, generous whitespace, neutral surfaces and restrained blue actions.
- Built a prominent liquidity overview: exact checking amount, confirmed timestamp, required reserve, eligible surplus and an SVG allocation ring driven by the same snapshot.
- Separated supporting yield/cost metrics from operational charts and financial detail tables.
- Restyled Shock Lab selectors, policy fields, before/after states and Arena comparisons consistently.
- Refined chart grids, tooltips, borders, controls and table spacing.
- Added mobile focus management, Escape dismissal, tab containment and inert background behavior; retained reduced-motion support.
- Removed external font requests. No new runtime dependency was added.

The mock ledger, API boundary, financial conventions and all three mandatory screens remain available. The expanded real API integration is still pending the backend contract.

References: https://www.apple.com/ and the user's supplied SONOTYPE prompt.

## First-visit presentation

The Command Center now opens with a full-height product introduction before a simulation exists. It uses oversized typography, an animated original treasury illustration, and a long scrolling story whose pinned visual switches between liquidity, stress testing, and strategy comparison. Each graphic is marked as simulated or illustrative; the strategy preview has no preset winner. A final call to action starts the same mock or real API workflow as the header control.

After a run starts, the detailed Command Center remains available with its balances, charts, transactions, decisions, and position terms. The story uses normal page scrolling, works at mobile widths, and reduces animation when the operating system requests less motion.

## Full-screen scene update — 2026-10-18

The updated landing page uses four full-width presentation scenes with scroll-linked
scale/translation, animated light fields and flow paths, chapter indicators, and a
reading progress line. The document owns scroll snapping; taller interactive panels
retain normal scrolling. Mobile navigation stays within the viewport. Reduced-motion
preferences disable scene transforms and snapping; the canvas draws a static frame
and pauses when the page is hidden.

The strategy introduction makes no return or safety guarantees. The landing sandbox
is an explicitly labeled frontend illustration with integer-cent arithmetic and no
executed trades. See MEMBER1_INTEGRATION_STATUS.md for the quantitative data boundary.

## Blur and reveal presentation

Scenes now pin while the next full-width sheet enters, with scroll-linked blur,
scale, opacity, and corner transitions. Tall scenes remain scrollable. Body overflow
uses clipping rather than an extra scroll container so sticky scenes work correctly.
The four-tier capital diagram supports keyboard and pointer selection with live
descriptions. Dashboard panels, allocation bars, buttons, and form controls have
restrained entrance and interaction feedback.

A visible pause control stops decorative CSS animations and scene effects.
System reduced-motion preferences also remove pinning, blur, and snapping. Motion
never changes simulated financial results or starts a run.

## Start states and CSV input

Replaced the obsolete welcome markup (whose styles were missing) with a scoped,
responsive card and animated capital-route illustration. Import controls appear
on both empty workspace screens and the landing page. The import dialog supports
keyboard focus, Escape, drag and drop, row-level validation, preview, and a template.
See CSV_INPUT.md for supported formats and the live ingestion boundary.

Scroll calculations now batch geometry reads before style writes. Scene blur is
lighter on mobile, content resize updates pinned heights, and dashboard navigation
uses a short opacity/position entrance without filtering the whole workspace.

## Separate landing and working screens

The product overview stays at `/` and remains the only document-scroll presentation.
The Command Center has its own `/command-center` route. Working screens use a
viewport-height shell: the taskbar, input action, and playback controls remain
visible while detailed content scrolls inside the main region. There is no scroll
snapping or chapter animation in the workspace.

Command Center views are Overview, Portfolio, Forecasts, and Activity. Their tablist
supports arrow keys, Home, and End with visible focus and labeled panels. Page
changes focus the main region and retain the shared simulation. Landing demo and
CSV actions enter the Command Center; returning to the product overview preserves
the run. CSV upload remains prominent, with short instructions for the next action.
