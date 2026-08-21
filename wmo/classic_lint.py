"""Classic (1.12 / vanilla) WMO export lint.

The 1.12 client renders WMO interiors strictly through the portal flood: when the
camera is inside a group that has no usable portal path to an EXTERIOR (0x8) group,
the whole outside world (terrain, sky, other WMOs) is skipped for the frame — the
player sees flat void through every opening. Verified by disassembly of the 1.12.1
(5875/Turtle) client. This module catches, at export time, every authoring mistake
that produced that symptom in practice:

  * portals silently not exported (objects outside the special 'Portals' collection);
  * half-linked portals (one group picker unset) — these also hard-crash the exporter
    downstream, so that abort applies to EVERY client version; fully-unlinked portals
    abort on Classic only (older exporter silently wrote a zeroed placeholder);
  * Indoor groups with zero portals (sealed rooms);
  * the ALWAYSDRAW (0x10000) group flag — the 1.12 portal flood EARLY-OUTS on such
    groups, so they seal even when portals exist (it is auto-stripped on Classic
    export by wmo_scene_group.py, with a warning here);
  * MOPR relations whose side could not be computed from either group (side=0);
  * geometric openings between an Indoor group and another group that no exported
    portal covers (the "door with no portal" / "roof seam" case).

Post-export checks run only for FULL Classic exports (PARTIAL exports skip groups,
which would make the checks lie). Everything except the half-linked-portal abort is
gated to Classic and does not change WotLK/Legion behavior.
"""

import bpy
import bmesh

from mathutils import Vector

from ..pywowlib import WoWVersions
from ..pywowlib.file_formats.wmo_format_group import MOGPFlags


class ClassicLintError(RuntimeError):
    """Raised to abort an export with a readable message instead of a crash."""
    pass


class ClassicLint:
    """Collector for Classic-export validation results (module-level singleton)."""

    enabled = False
    errors = []
    warnings = []
    infos = []

    # ------------------------------------------------------------------ state

    @classmethod
    def reset(cls, client_version: int):
        cls.enabled = client_version < WoWVersions.WOTLK
        cls.errors = []
        cls.warnings = []
        cls.infos = []

    @classmethod
    def error(cls, msg: str):
        if cls.enabled:
            cls.errors.append(msg)

    @classmethod
    def warn(cls, msg: str):
        if cls.enabled:
            cls.warnings.append(msg)

    @classmethod
    def info(cls, msg: str):
        if cls.enabled:
            cls.infos.append(msg)

    # ------------------------------------------------------------------ checks

    @classmethod
    def pre_checks(cls, bl_scene):
        """Runs after build_references(), before any group/portal is saved.

        A HALF-linked portal (exactly one group picker set) crashes save_portals()
        with an AttributeError on any client version — abort readably instead.
        A FULLY-unlinked portal exported silently as a zeroed placeholder before,
        so it aborts on Classic only (where the placeholder is a real hazard).
        """

        half, unlinked = [], []
        for portal_obj in bl_scene.bl_portals:
            pg = portal_obj.wow_wmo_portal
            desc = "'%s' (First: %s, Second: %s)" % (
                portal_obj.name,
                pg.first.name if pg.first else "none",
                pg.second.name if pg.second else "none")
            if bool(pg.first) != bool(pg.second):
                half.append(desc)
            elif not pg.first and not pg.second:
                unlinked.append(desc)

        aborting = half + (unlinked if cls.enabled else [])
        if aborting:
            # bypass the `enabled` gate: this abort must render in the popup too
            for d in aborting:
                cls.errors.append("Portal not linked to two groups: " + d)
            raise ClassicLintError(
                "WMO export aborted: portal(s) not linked to two groups.\n"
                "Select each portal and set BOTH pickers in Object Properties -> WMO Portal:\n"
                + "\n".join("  - " + d for d in aborting))

        # portal-like meshes that will NOT be exported (outside any Portals collection).
        # Classic-only warning; objects sitting in ANY 'Portals' collection are skipped,
        # so a second WMO model collection in the scene does not produce false alarms.
        exported = {obj.name for obj in bl_scene.bl_portals}
        for obj in bpy.context.scene.objects:
            if obj.type != 'MESH' or obj.name in exported:
                continue
            if any(c.name.split('.')[0] == 'Portals' for c in obj.users_collection):
                continue
            pg = getattr(obj, 'wow_wmo_portal', None)
            if pg is not None and (pg.first or pg.second):
                cls.warn("Portal-like object '%s' is NOT in the model's 'Portals' collection "
                         "— it will NOT be exported. Move it there." % obj.name)

    @classmethod
    def post_checks(cls, bl_scene):
        """Runs after save_portals()/save_groups(), before the file is written.
        Classic + FULL export only. Raises ClassicLintError on hard errors."""

        if not cls.enabled:
            return
        if not getattr(bl_scene.wmo, 'export', True):
            cls.info("Classic lint: post-export checks skipped for PARTIAL export.")
            return

        wmo = bl_scene.wmo
        n_portals = len(wmo.mopt.infos)
        cls.info("Exported %d portal(s), %d group(s)." % (n_portals, len(bl_scene.bl_groups)))

        has_indoor = False
        for bl_group in bl_scene.bl_groups:
            mogp = bl_group.wmo_group.mogp
            name = bl_group.bl_object.name
            if mogp.flags & MOGPFlags.Indoor:
                has_indoor = True
                if mogp.portal_count == 0:
                    cls.warn("[1.12] Indoor group '%s' has NO portals — in the 1.12 client the room "
                             "will be SEALED: no sky/terrain/world visible from inside. Add a portal "
                             "quad for each opening (door, window) in the 'Portals' collection." % name)

        if n_portals and not has_indoor:
            cls.warn("[1.12] The model has %d portal(s) but NO Indoor group — portals are useless "
                     "and the interior/exterior render split will not work. Put the interior mesh "
                     "in the Indoor collection." % n_portals)

        for i, rel in enumerate(wmo.mopr.relations):
            if rel.side == 0:
                pname = (bl_scene.bl_portals[rel.portal_index].name
                         if rel.portal_index < len(bl_scene.bl_portals) else '#%d' % rel.portal_index)
                cls.error("Portal '%s': direction could not be computed from either side (side=0) "
                          "— the 1.12 client will cull it wrongly. Select the portal and set "
                          "WMO Portal -> Algorithm to Positive or Negative manually." % pname)

        try:
            cls._detect_uncovered_openings(bl_scene)
        except Exception as e:  # the detector must never break an export
            cls.warn("Opening detector skipped (%s: %s)." % (type(e).__name__, e))

        if cls.errors:
            raise ClassicLintError("WMO export aborted — Classic (1.12) lint errors:\n"
                                   + "\n".join("  - " + e for e in cls.errors))

    # ------------------------------------------------- opening detector

    _QUANT = 4.0          # snap grid 1/4 unit for coincidence tests
    _MAX_VERTS = 200000   # skip pathological meshes
    _INFLATE = 1.0        # portal-coverage bbox inflation
    _MAX_WARN_PER_PAIR = 5

    @classmethod
    def _detect_uncovered_openings(cls, bl_scene):
        """Find geometric openings shared by two groups (coincident boundary-edge
        loops, e.g. a doorway frame present in both the shell and the room) that no
        exported portal covers, and warn with coordinates. Uses depsgraph-EVALUATED
        meshes so modifier results match what was actually exported."""

        depsgraph = bpy.context.evaluated_depsgraph_get()

        def qv(v):
            return (round(v.x * cls._QUANT) / cls._QUANT,
                    round(v.y * cls._QUANT) / cls._QUANT,
                    round(v.z * cls._QUANT) / cls._QUANT)

        skipped = []

        def boundary_edges(obj):
            """[(edge_key, (world_a, world_b)), ...] for evaluated edges with 1 face."""
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.data
            if len(mesh.vertices) > cls._MAX_VERTS:
                skipped.append(obj.name)
                return []
            bm = bmesh.new()
            bm.from_mesh(mesh)
            mw = obj_eval.matrix_world
            out = []
            for e in bm.edges:
                if len(e.link_faces) == 1:
                    a = mw @ e.verts[0].co
                    b = mw @ e.verts[1].co
                    out.append((frozenset((qv(a), qv(b))), (a.copy(), b.copy())))
            bm.free()
            return out

        groups = [g.bl_object for g in bl_scene.bl_groups]
        indoor = {g.bl_object.name: bool(g.wmo_group.mogp.flags & MOGPFlags.Indoor)
                  for g in bl_scene.bl_groups}
        # name -> (key set, [(key, seg), ...]); key sets precomputed once per group
        edges = {}
        for obj in groups:
            be = boundary_edges(obj)
            edges[obj.name] = ({k for k, _ in be}, be)

        # portal AABBs (evaluated, world space) — overlap test beats centroid-in-box
        portal_boxes = []
        for pobj in bl_scene.bl_portals:
            pobj_eval = pobj.evaluated_get(depsgraph)
            mw = pobj_eval.matrix_world
            pts = [mw @ v.co for v in pobj_eval.data.vertices]
            if pts:
                portal_boxes.append((
                    Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
                    Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))))

        def covered(lo, hi):
            for plo, phi in portal_boxes:
                if (plo.x <= hi.x + cls._INFLATE and phi.x >= lo.x - cls._INFLATE and
                        plo.y <= hi.y + cls._INFLATE and phi.y >= lo.y - cls._INFLATE and
                        plo.z <= hi.z + cls._INFLATE and phi.z >= lo.z - cls._INFLATE):
                    return True
            return False

        pairs_checked = 0
        openings_found = 0
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                gi, gj = groups[i].name, groups[j].name
                if not (indoor.get(gi) or indoor.get(gj)):
                    continue  # openings only matter when an interior is involved
                pairs_checked += 1
                keys_i = edges[gi][0]
                shared = [(k, seg) for k, seg in edges[gj][1] if k in keys_i]
                if len(shared) < 3:
                    continue
                pair_warned = 0
                for comp in cls._components(shared):
                    if len(comp) < 3:
                        continue
                    openings_found += 1
                    pts = [Vector(p) for seg in comp for p in seg]
                    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
                    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
                    if not covered(lo, hi):
                        pair_warned += 1
                        if pair_warned <= cls._MAX_WARN_PER_PAIR:
                            center = (lo + hi) / 2.0
                            ext = sorted((hi - lo)[:], reverse=True)
                            cls.warn("[1.12] Opening between '%s' and '%s' at (%.1f, %.1f, %.1f), "
                                     "~%.1f x %.1f — NO portal covers it. Looking through it from "
                                     "inside will show void. Add a portal quad there."
                                     % (gi, gj, center.x, center.y, center.z, ext[0], ext[1]))
                if pair_warned > cls._MAX_WARN_PER_PAIR:
                    cls.warn("[1.12] ...and %d more uncovered opening(s) between '%s' and '%s'."
                             % (pair_warned - cls._MAX_WARN_PER_PAIR, gi, gj))

        stats = ("Opening detector: %d group pair(s) checked, %d shared opening(s) found."
                 % (pairs_checked, openings_found))
        if skipped:
            stats += " Skipped oversized group(s): %s." % ", ".join(skipped)
        cls.info(stats)

    @staticmethod
    def _components(shared_edges):
        """Group edges into connected components by shared quantized endpoints.
        Returns a list of components, each a list of (world_a, world_b) segments."""
        parent = {}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for key, _seg in shared_edges:
            for p in key:
                parent.setdefault(p, p)
        for key, _seg in shared_edges:
            pts = list(key)
            for k in range(1, len(pts)):
                union(pts[0], pts[k])

        comps = {}
        for key, seg in shared_edges:
            root = find(next(iter(key)))
            comps.setdefault(root, []).append(seg)
        return list(comps.values())

    # ------------------------------------------------------------------ UI

    _MAX_POPUP_LINES = 40

    @classmethod
    def report_lines(cls):
        return (["ERROR: " + m for m in cls.errors]
                + ["WARNING: " + m for m in cls.warnings]
                + [m for m in cls.infos])

    @classmethod
    def show_popup(cls):
        lines = cls.report_lines()
        if not lines:
            return
        shown = lines[:cls._MAX_POPUP_LINES]
        if len(lines) > cls._MAX_POPUP_LINES:
            shown.append("... %d more line(s) — see the system console / Info log."
                         % (len(lines) - cls._MAX_POPUP_LINES))

        def draw(menu, _context):
            col = menu.layout.column()
            for line in shown:
                # popup rows are single-line; wrap long messages crudely
                text = line
                while len(text) > 110:
                    col.label(text=text[:110])
                    text = '    ' + text[110:]
                col.label(text=text)

        icon = 'ERROR' if (cls.errors or cls.warnings) else 'INFO'
        try:
            bpy.context.window_manager.popup_menu(draw, title="WMO Classic (1.12) lint", icon=icon)
        except Exception:
            pass  # headless/background run — console output only
