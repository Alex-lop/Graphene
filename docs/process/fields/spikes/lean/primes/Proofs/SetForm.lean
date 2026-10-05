import Challenge

theorem set_form (h : S_root) : S_root_set := by
  apply Set.infinite_of_forall_exists_gt
  intro n
  obtain ⟨p, hnp, hp, hp3⟩ := h n
  exact ⟨p, ⟨hp, hp3⟩, hnp⟩
