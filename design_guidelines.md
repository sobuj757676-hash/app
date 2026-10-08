{
  "design_system_name": "Unit-First Daily Plan (Tracker-Integrated)",
  "product_intent": {
    "app_type": "operational construction project app (supervisor planning + field execution)",
    "primary_users": [
      "Site supervisors (plan quickly, one-handed on 390px)",
      "Field workers (see today’s queue in <5s, execute + confirm)",
      "Project managers/admins (auditability, exceptions, reschedule/carry)"
    ],
    "north_star": "Daily Plan is a planning layer on top of Unit Tracker; Unit Tracker remains the source of truth for unit stage/status. Daily Plan shows: Today, these real units need this real work, assigned to these people.",
    "ux_success_in_5_seconds": [
      "What is planned today?",
      "Where is the work (Block + Level)?",
      "What work type/stage?",
      "How many units + which unit IDs?",
      "Who is responsible?",
      "What’s the priority (secondary)?",
      "What’s completed vs remaining?",
      "What needs attention (blocked, stale, conflicts)?"
    ]
  },

  "visual_personality": {
    "keywords": [
      "calm industrial",
      "neutral surfaces",
      "high legibility in sun/glare",
      "truthful status colors",
      "location-first hierarchy",
      "mobile-first, thumb-friendly"
    ],
    "do_not": [
      "Do not introduce a new brand palette that diverges from Unit Tracker.",
      "Do not use decorative gradients beyond small section accents (<=20% viewport).",
      "Do not create a second ‘task system’ look; Daily Plan must feel like the same product as Unit Tracker.",
      "Do not use emoji icons; use lucide-react or FontAwesome only."
    ]
  },

  "design_tokens": {
    "source_of_truth": "Use existing CSS variables in /app/frontend/src/index.css. Do not replace them; only add scoped tokens if needed.",
    "existing_css_vars": {
      "surfaces": {
        "page": "var(--page)",
        "surface": "var(--surface)",
        "soft": "var(--soft)",
        "line": "var(--line)"
      },
      "text": {
        "text": "var(--text)",
        "muted": "var(--muted-text)"
      },
      "semantic": {
        "info": "var(--info)",
        "info_soft": "var(--info-soft)",
        "success": "var(--success)",
        "success_soft": "var(--success-soft)",
        "warning": "var(--warning)",
        "warning_soft": "var(--warning-soft)",
        "danger": "var(--danger)",
        "danger_soft": "var(--danger-soft)",
        "blue": "var(--blue)",
        "blue_soft": "var(--blue-soft)"
      },
      "radius": "var(--radius)"
    },
    "scoped_additions_allowed": {
      "note": "If Daily Plan needs extra nuance (e.g., ‘attention’ background), add ONLY scoped CSS variables under a .plan namespace (e.g., .plan { --plan-attn-bg: ... }).",
      "recommended_scoped_vars": {
        "--plan-card-radius": "12px",
        "--plan-chip-radius": "999px",
        "--plan-sticky-blur": "8px",
        "--plan-shadow": "0 10px 30px rgba(0,0,0,0.06)",
        "--plan-shadow-hover": "0 14px 40px rgba(0,0,0,0.08)"
      }
    }
  },

  "typography": {
    "fonts_in_use": {
      "headings": "Outfit (already imported)",
      "body": "Manrope (already imported)",
      "mono": "JetBrains Mono (already imported)",
      "i18n": "Noto Sans Bengali, Noto Sans SC (already imported)"
    },
    "hierarchy": {
      "page_h1": "text-[28px] leading-[1.25] font-[550] (matches .page-title h1)",
      "section_h2": "text-[18px] font-[500]",
      "card_title": "text-[14px] font-[650]",
      "supporting": "text-[11px] text-[var(--muted-text)]",
      "micro": "text-[9px] tracking-[0.06em] uppercase for labels only",
      "unit_id": "font: 11px JetBrains Mono; use for chips and IDs"
    },
    "rules": [
      "Never center-align long reading content; keep left alignment.",
      "Use mono ONLY for unit IDs, stage indices, and compact counts.",
      "Avoid shrinking below 11px for critical info on mobile; 9–10px only for labels/badges."
    ]
  },

  "layout_and_grid": {
    "mobile_first": {
      "target_width": "390px",
      "content_padding": "match .main-content mobile padding (18px; 13px under 380px)",
      "tap_targets": "Primary actions 44–48px min height; icon buttons 40px on coarse pointers (already in App.css)",
      "structure": [
        "Top: date + progress strip (compact)",
        "Then: Today’s Work grouped by Block -> Level",
        "Each group: Work Cards (stage/work type) with unit chips + crew + primary action",
        "Bottom: sticky selection/save bars must sit above mobile bottom nav safe area"
      ]
    },
    "desktop": {
      "max_width": "Use existing .main-content max-width 1800px",
      "columns": "Prefer 1 column for clarity; allow 2-column card grid only when it improves scanning (e.g., many work cards under same block).",
      "avoid": "Do not introduce a 3-pane planner that duplicates inventory; keep Tracker as the selection surface."
    },
    "information_hierarchy": {
      "location_first": [
        "Block name (largest)",
        "Level (secondary)",
        "Work type / Stage name (card title)",
        "Unit count + unit chips",
        "Crew + priority badge",
        "Next stage hint (progressive disclosure)",
        "Notes/target (collapsed by default)"
      ]
    }
  },

  "daily_plan_screen_blueprint": {
    "screen_name": "Daily Plan (paired with Unit Tracker)",
    "route_guidance": {
      "canonical": "/units?view=plan&date=YYYY-MM-DD",
      "legacy": "/tasks?tab=plan redirects",
      "nav_rule": "No new top-level nav item; Daily Plan is a paired view within Unit Tracker context."
    },
    "top_area": {
      "date_control": {
        "component": "shadcn Popover + Calendar",
        "component_path": "/app/frontend/src/components/ui/popover.jsx + /app/frontend/src/components/ui/calendar.jsx",
        "behavior": [
          "Date is sticky in URL query and preserved when switching between Units and Plan views.",
          "One-tap ‘Today’ shortcut.",
          "On mobile: date control is a single button opening a bottom Drawer (Sheet) with Calendar."
        ],
        "data_testid": "daily-plan-date-picker"
      },
      "progress_strip": {
        "component": "shadcn Card + Progress",
        "component_path": "/app/frontend/src/components/ui/card.jsx + /app/frontend/src/components/ui/progress.jsx",
        "content": [
          "Planned units",
          "In progress",
          "Completed",
          "Remaining",
          "Needs attention (if any)"
        ],
        "visual": [
          "Use neutral surface; use semantic colors only for small pills/dots.",
          "Avoid big dashboard tiles; keep it one compact strip."
        ],
        "data_testid": "daily-plan-progress-strip"
      }
    },
    "main_content": {
      "grouping": "Block -> Level -> Work Card (Stage/Work Type).",
      "work_card": {
        "component": "shadcn Card + Badge + Button + Collapsible",
        "component_path": [
          "/app/frontend/src/components/ui/card.jsx",
          "/app/frontend/src/components/ui/badge.jsx",
          "/app/frontend/src/components/ui/button.jsx",
          "/app/frontend/src/components/ui/collapsible.jsx",
          "/app/frontend/src/components/PlanUnitChips.jsx"
        ],
        "card_header": [
          "Stage/Work name (Outfit, 14–15px, 650)",
          "Unit count (mono) e.g., ‘4 units’",
          "Crew summary (Assignees avatars/initials + optional team label)",
          "Priority badge (small, not dominant)"
        ],
        "card_body": [
          "Unit chips row (scrollable horizontally if needed; never wrap into 6 lines on mobile—use ‘+N more’ collapse)",
          "Status line: ‘2/4 completed’ derived from real unit receipts",
          "Optional: ‘Next: <stage name>’ hint (muted)"
        ],
        "card_actions": {
          "primary": "Start / Continue",
          "secondary": [
            "Complete selected units",
            "Edit plan",
            "Reschedule / Carry remaining",
            "Cancel remaining"
          ],
          "rules": [
            "Workers see only Start/Complete + unit chips; supervisors see Edit/Reschedule/Cancel.",
            "Primary action is full-width on mobile.",
            "Never show destructive actions as primary; keep them in a dropdown or confirm dialog."
          ]
        },
        "attention_states": {
          "blocked": "Show a compact Alert row inside card (danger-soft) with reason + ‘Open unit’ link.",
          "stale": "If unit stage changed since planning, show warning-soft ‘Needs review’ and list affected unit chips.",
          "conflict": "If unit appears in another active plan, show warning-soft with link to that plan date."
        },
        "data_testids": {
          "card": "daily-plan-work-card",
          "start_button": "daily-plan-work-card-start-button",
          "complete_button": "daily-plan-work-card-complete-button",
          "edit_button": "daily-plan-work-card-edit-button",
          "more_menu": "daily-plan-work-card-more-menu"
        }
      },
      "empty_states": {
        "no_plans_today": {
          "pattern": "Centered empty block (already styled as .empty) but with left-aligned text inside card for readability.",
          "content": [
            "Title: ‘No work planned for today’",
            "Body: ‘Go to Units, filter Ready work, select units, then Add to Today’s Plan.’",
            "CTA: ‘Open Unit Tracker’"
          ],
          "component": "shadcn Card + Button",
          "data_testid": "daily-plan-empty-state"
        },
        "no_results_after_filters": {
          "content": [
            "Title: ‘Nothing matches these filters’",
            "Body: ‘Try removing Stage or Block filters.’",
            "CTA: ‘Clear filters’"
          ],
          "data_testid": "daily-plan-no-results"
        }
      }
    }
  },

  "unit_tracker_to_plan_workflow_ui": {
    "entry_point": "Unit Tracker selection mode is the planning surface.",
    "selection_affordances": [
      "Select visible (bulk) button",
      "Selection count pill (sticky)",
      "Clear selection",
      "Add to Today’s Plan (primary)"
    ],
    "composer": {
      "pattern": "Single shared composer sheet (Drawer/Sheet) that previews grouping before save.",
      "component_path": [
        "/app/frontend/src/components/ui/drawer.jsx or /app/frontend/src/components/ui/sheet.jsx",
        "/app/frontend/src/components/AssigneeMultiSelect.jsx",
        "/app/frontend/src/components/PlanUnitChips.jsx",
        "/app/frontend/src/components/ui/select.jsx",
        "/app/frontend/src/components/ui/textarea.jsx"
      ],
      "fields": {
        "planned_date": "default = selected date in Daily Plan; editable",
        "stage_or_work": "default inferred from selected units’ current valid next stage; if mixed, auto-split preview",
        "assignees": "AssigneeMultiSelect (existing users)",
        "team_label": "optional free text (short)",
        "priority": "High/Medium/Low (small select)",
        "target": "optional numeric or short text (e.g., ‘Complete all 4’)",
        "notes": "optional; multiline"
      },
      "group_preview": {
        "must_show": [
          "Block + Level",
          "Stage/work name",
          "Unit chips",
          "Count",
          "Any excluded units with reasons (blocked, wrong stage, already planned)"
        ],
        "interaction": [
          "Allow removing a unit chip from the selection inside the composer.",
          "Do not require naming the plan item; title is derived from location + stage."
        ]
      },
      "footer_actions": {
        "primary": "Save plan",
        "secondary": "Cancel",
        "placement": "Sticky footer above safe area; never hidden behind bottom nav.",
        "data_testids": {
          "save": "daily-plan-composer-save-button",
          "cancel": "daily-plan-composer-cancel-button"
        }
      }
    }
  },

  "components_to_use": {
    "shadcn_primary": [
      {
        "name": "Button",
        "path": "/app/frontend/src/components/ui/button.jsx",
        "usage": "Primary actions (.action class in App.css) for consistency"
      },
      {
        "name": "Card",
        "path": "/app/frontend/src/components/ui/card.jsx",
        "usage": "Work cards, progress strip containers"
      },
      {
        "name": "Badge",
        "path": "/app/frontend/src/components/ui/badge.jsx",
        "usage": "Priority, status, ‘Needs attention’"
      },
      {
        "name": "Drawer / Sheet",
        "path": "/app/frontend/src/components/ui/drawer.jsx and /app/frontend/src/components/ui/sheet.jsx",
        "usage": "Mobile composer + date picker + edit plan"
      },
      {
        "name": "Dialog / AlertDialog",
        "path": "/app/frontend/src/components/ui/dialog.jsx and /app/frontend/src/components/ui/alert-dialog.jsx",
        "usage": "Confirm cancel/reschedule/complete selected"
      },
      {
        "name": "Popover + Calendar",
        "path": "/app/frontend/src/components/ui/popover.jsx and /app/frontend/src/components/ui/calendar.jsx",
        "usage": "Desktop date picker"
      },
      {
        "name": "Tabs",
        "path": "/app/frontend/src/components/ui/tabs.jsx",
        "usage": "Paired Units / Daily Plan view switch (or reuse existing TabBar)"
      },
      {
        "name": "DropdownMenu",
        "path": "/app/frontend/src/components/ui/dropdown-menu.jsx",
        "usage": "More actions on work card"
      },
      {
        "name": "Progress",
        "path": "/app/frontend/src/components/ui/progress.jsx",
        "usage": "Compact completion indicator"
      },
      {
        "name": "ScrollArea",
        "path": "/app/frontend/src/components/ui/scroll-area.jsx",
        "usage": "Unit chips horizontal scroll + long lists in sheets"
      },
      {
        "name": "Sonner",
        "path": "/app/frontend/src/components/ui/sonner.jsx",
        "usage": "Toasts for save/complete/reschedule results"
      },
      {
        "name": "Alert",
        "path": "/app/frontend/src/components/ui/alert.jsx",
        "usage": "Inline blockers + stale warnings"
      }
    ],
    "existing_app_components_to_respect": [
      {
        "name": "TabBar",
        "path": "/app/frontend/src/components/TabBar.jsx",
        "note": "Preserve existing mobile bottom navigation patterns; do not introduce a new nav paradigm."
      },
      {
        "name": "AssigneeMultiSelect",
        "path": "/app/frontend/src/components/AssigneeMultiSelect.jsx",
        "note": "Use for crew assignment; do not invent a new team model UI."
      },
      {
        "name": "PlanUnitChips",
        "path": "/app/frontend/src/components/PlanUnitChips.jsx",
        "note": "Use for unit chip rendering; extend behavior (collapse/+N) rather than replacing."
      },
      {
        "name": "UnitDrawer",
        "path": "/app/frontend/src/components/UnitDrawer.jsx",
        "note": "Unit details must open here; Daily Plan should not duplicate unit detail screens."
      }
    ]
  },

  "component_specs": {
    "work_card_spec": {
      "container_classes": "bg-[var(--surface)] border border-[var(--line)] rounded-[12px] shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:shadow-[0_10px_30px_rgba(0,0,0,0.06)]",
      "header_layout": "flex items-start justify-between gap-3",
      "title_classes": "text-[14px] font-[650] text-[var(--text)]",
      "meta_line_classes": "text-[11px] text-[var(--muted-text)]",
      "unit_chip_row": "flex gap-2 overflow-x-auto py-1",
      "chip_classes": "inline-flex items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--page)] px-3 py-2 text-[12px]",
      "primary_button": "Use existing .action class for primary CTA; ensure min-height 44px on mobile",
      "priority_badge": "Use .priority-tag styles already in App.css; keep small and right-aligned",
      "attention_alert": "bg-[var(--warning-soft)] text-[var(--warning)] border border-[color-mix(in_srgb,var(--warning)_25%,transparent)] rounded-[10px] px-3 py-2 text-[12px]"
    },
    "sticky_footer_spec": {
      "purpose": "Selection count + Save/Cancel always reachable while scrolling",
      "classes": "sticky bottom-0 z-10 bg-[color-mix(in_srgb,var(--surface)_92%,transparent)] backdrop-blur-[8px] border-t border-[var(--line)]",
      "safe_area": "Add padding-bottom using env(safe-area-inset-bottom) when available",
      "data_testid": "daily-plan-sticky-footer"
    },
    "unit_chip_collapse": {
      "rule": "If > 8 chips on mobile, show first 6 + ‘+N more’ chip that expands Collapsible.",
      "expanded_state": "Expanded list uses ScrollArea with max-height to avoid page jump.",
      "data_testids": {
        "chip": "daily-plan-unit-chip",
        "more": "daily-plan-unit-chip-more"
      }
    }
  },

  "motion_and_microinteractions": {
    "principles": [
      "Motion must confirm state changes (save/complete/reschedule) and improve scanning, not decorate.",
      "Respect prefers-reduced-motion (already handled globally).",
      "Never use transition: all."
    ],
    "recommended_interactions": {
      "card_hover_desktop": "translateY(-2px) + subtle shadow (already used in .block-card and .unit-cell patterns)",
      "press_state": "active:scale-[0.98] on primary buttons only",
      "chip_interaction": "chips highlight on hover/focus; selected chips use var(--blue-soft) background",
      "loading": "Use shadcn Skeleton for plan list and composer preview; avoid spinners for long lists"
    },
    "toast_usage": {
      "library": "sonner",
      "patterns": [
        "Success: ‘Plan saved’ + count",
        "Partial completion: ‘2 completed, 1 blocked’ with ‘View details’ action",
        "Error: actionable message, never generic ‘failed’"
      ]
    }
  },

  "accessibility_and_field_conditions": {
    "contrast": [
      "Maintain WCAG AA contrast for text on surfaces.",
      "Do not rely on color alone for status; pair with label text (e.g., ‘Blocked’, ‘Needs review’)."
    ],
    "field_use": [
      "Prefer solid backgrounds; avoid low-contrast hairlines in bright sun.",
      "Keep critical actions large and separated (avoid adjacent destructive actions).",
      "Use sticky headers/footers sparingly to preserve content space."
    ],
    "focus": "Use existing focus-visible outline (2px var(--blue), offset 3px). Ensure all custom clickable divs are converted to buttons/links.",
    "i18n": [
      "Allow longer strings (ZH/BN) by avoiding fixed widths on labels.",
      "Use truncation only for secondary metadata; never truncate Block/Level/Stage in the primary header without a tooltip or wrap."
    ]
  },

  "testing_attributes": {
    "rule": "All interactive and key informational elements MUST include data-testid (kebab-case, role-based).",
    "minimum_required_testids": [
      "daily-plan-date-picker",
      "daily-plan-progress-strip",
      "daily-plan-work-card",
      "daily-plan-work-card-start-button",
      "daily-plan-work-card-complete-button",
      "daily-plan-work-card-edit-button",
      "daily-plan-work-card-more-menu",
      "daily-plan-unit-chip",
      "daily-plan-unit-chip-more",
      "daily-plan-composer-save-button",
      "daily-plan-composer-cancel-button",
      "daily-plan-empty-state",
      "daily-plan-sticky-footer"
    ]
  },

  "image_urls": {
    "note": "No new decorative imagery required; this is a field operations tool. Keep surfaces clean and fast. If a banner image exists elsewhere, reuse existing project banner patterns; do not add new stock photos to Daily Plan.",
    "categories": []
  },

  "additional_libraries": {
    "required": [],
    "optional": [
      {
        "name": "framer-motion",
        "why": "Optional for subtle entrance animations on desktop only; not required because existing CSS animations already cover page enter and progress bars.",
        "install": "npm i framer-motion",
        "usage_note": "If used, keep motion minimal and disable on prefers-reduced-motion."
      }
    ]
  },

  "instructions_to_main_agent": [
    "Preserve existing tokens in index.css and existing component styling patterns in App.css; Daily Plan should look like Unit Tracker.",
    "Implement Daily Plan as a location-first grouped view: Block -> Level -> Work Card (stage/work type).",
    "Do not duplicate unit state in Daily Plan UI; completion/progress must be derived from authoritative unit updates/receipts.",
    "Use Unit Tracker as the selection surface; Daily Plan composer is a single shared sheet that previews grouping and exclusions.",
    "Mobile-first: single column, large actions (>=44px), sticky save footer above bottom nav.",
    "Use shadcn/ui components from /src/components/ui (JSX) only; do not introduce raw HTML dropdown/calendar/toast.",
    "Use sonner for toasts.",
    "Add data-testid to every interactive element and key info label/value.",
    "Avoid gradients except small, mild section accents; never exceed 20% viewport and never on reading areas.",
    "No AI features."
  ],

  "general_ui_ux_design_guidelines_appendix": "- You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n- You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n- NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals."
}
