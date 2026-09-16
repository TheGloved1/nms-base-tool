#!/usr/bin/env python3
"""Launch GTK GUI (default) - use --tui for old Textual TUI."""
import sys
if "--tui" in sys.argv:
    sys.argv.remove("--tui")
    from nms_tui.app import main
else:
    from nms_gtk.app import main
if __name__ == "__main__":
    main()
