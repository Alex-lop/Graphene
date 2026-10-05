import Proofs.SqMod4
import Proofs.SumTwoSq

theorem root : S_root := by
  rintro n hn ⟨a, b, hab⟩
  have := sumTwoSq sqMod4 a b
  omega
