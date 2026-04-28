// Package beads -- single-hooked-bead-per-(assignee, formula) invariant.
//
// Helpers used by gt sling to close existing same-formula hooked beads before
// hooking a new one. Enforces the singleton-by-formula contract at the sling
// boundary; see gastown #3768.

package beads

import "fmt"

// CloseSameFormulaHookedSiblings closes any existing beads on the given assignee
// that are in `hooked` status with the same attached formula. Returns the IDs
// it closed (for caller logging) or an error.
//
// The single-formula-per-assignee invariant is enforced at the sling boundary:
// a new sling for (assignee, formula) closes any prior hooked beads for that
// same tuple before the new bead is hooked. The caller MUST hold the per-
// assignee sling lock (tryAcquireSlingAssigneeLock) so that "close-old, hook-
// new" is atomic from the perspective of any concurrent sling on the same
// assignee. See gastown #3768.
//
// Protected beads (gt:standing-orders, gt:keep, gt:role, gt:rig) are skipped:
// these labels mean the bead is intentionally pinned regardless of formula
// churn. If a future need arises to override protection here, do it explicitly
// with a separate force variant.
//
// Returns (nil, nil) on the common path where there are no matching siblings.
// Empty formulaName is treated as "no formula key to enforce against" and
// returns (nil, nil) immediately -- plain (raw-bead) slings have no formula
// singleton to maintain.
func (b *Beads) CloseSameFormulaHookedSiblings(assignee, formulaName string) ([]string, error) {
	if formulaName == "" {
		return nil, nil
	}
	if assignee == "" {
		return nil, nil
	}

	issues, err := b.List(ListOptions{
		Status:   string(IssueStatusHooked),
		Assignee: assignee,
	})
	if err != nil {
		return nil, fmt.Errorf("listing hooked beads for %s: %w", assignee, err)
	}

	var ids []string
	for _, issue := range issues {
		if issue == nil {
			continue
		}
		if IsProtectedBead(issue) {
			continue
		}
		fields := ParseAttachmentFields(issue)
		if fields == nil || fields.AttachedFormula != formulaName {
			continue
		}
		ids = append(ids, issue.ID)
	}

	if len(ids) == 0 {
		return nil, nil
	}

	reason := fmt.Sprintf(
		"superseded by new sling for formula %q on %s (gastown #3768)",
		formulaName, assignee,
	)
	if err := b.CloseWithReason(reason, ids...); err != nil {
		return nil, fmt.Errorf("closing superseded hooks %v: %w", ids, err)
	}
	return ids, nil
}
