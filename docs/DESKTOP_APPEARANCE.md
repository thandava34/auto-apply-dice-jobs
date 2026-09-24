# Desktop appearance rollout

Both existing Tkinter applications use the approved Jobs & Contacts visual
direction. No replacement launcher, website, application-state simulation or
new package was added.

## Implementation boundaries

- `utils/desktop_tokens.py` defines the shared palette and typography.
- `utils/desktop_theme.py` applies general ttk styles and normalizes legacy Tk
  widget fonts and neutral colours after the existing builders finish.
- Newly mapped custom-dialog widgets receive styling once. There is no theme
  polling, worker, network access or ongoing animation.
- The existing tab IDs, widget parents, commands, variables and saved records
  remain intact. Shorter tab labels preserve available screen space.
- Jobs & Contacts retains its scoped two-line rows, complete cached records and
  existing calling/search/link behaviour.

## Visual decisions

Dice uses blue for starting actions; Nvoids uses teal. Stop is red, calling
actions green, caution amber and secondary controls slate. Disabled states are
dark with readable muted labels, and keyboard focus has a visible border.
Neutral panels keep status colours meaningful. Static action/section labels
lose decorative emoji; real status messages are not rewritten.

Segoe UI body text is 11 pt, supporting text at least 10 pt, and existing larger
headings/counters are retained. Font sizes use Tk points without changing the
Windows/Tk scaling factor. Tables size rows from measured text height. Named
buttons share padding. Nvoids dashboard actions occupy two rows to reduce width
pressure. Toggle switches support Tab, Space and Enter through their existing
callback/variable path.

## Validation and limitations

The rollout regression run passed 104 tests and 3 provider subtests. Five existing
SWIG deprecation warnings remain. Test groups now share one Tcl interpreter to
avoid intermittent repeated-interpreter initialization failures on this machine.

Offline tests verify state/command/value preservation, later-dialog styling,
bot accents, disabled/focus states, unchanged scaling and keyboard toggles.
Existing Jobs & Contacts tests cover selection, links, calling scope, search,
saved input and laptop-size geometry. These checks are not visual certification
of every dense legacy screen at every Windows display scale.

Native Windows message boxes and file pickers retain OS styling. Existing error
wording and provider activity reporting remain unchanged. This rollout does not
claim to redesign backend error handling or revalidate live mail delivery.
Restart idle apps to load the new appearance, then review them on the actual
monitor before requesting further layout changes.
