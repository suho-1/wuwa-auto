"""wuwa-auto terminal interface.

The dashboard is a single fixed-height frame that repaints in place: the
activity log updates and the clock ticks on their own, and the terminal never
scrolls. That contract is enforced by tests rather than assumed -- see
``tests/test_tui_frame.py``, which renders the real frame across a matrix of
terminal sizes and asserts that every line is exactly the frame width and the
row count never exceeds the terminal height.

``console``       terminal plumbing: width, height, in-place frame drawing, prompts
``keys``          cross-platform single-key input and a one-line editor
``logs``          thread-safe ring buffer fed by the engine's log bus
``config_store``  mtime-cached, atomically written task config files
``grid``          fixed-width table and panel primitives (no per-cell measuring)
``layout``        the frame budget: which sections fit, and what was hidden
``engine``        the only module that touches the live OK-WW engine
``routines``      declarative trigger/routine tables and target summaries
``dashboard``     the main frame and the static reference views
``livestream``    log tailing and one-time routine monitoring
``config_menu``   pickers for choosing what each routine farms
``templates``     screenshot capture, annotation, export and deletion
``app``           command registry, live REPL loop and shutdown
"""

from .app import OKWWAdvancedTUI, run_tui

__all__ = ["OKWWAdvancedTUI", "run_tui"]
