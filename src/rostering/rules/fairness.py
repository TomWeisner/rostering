import numpy as np

from rostering.rules.base import Rule


class FairnessRule(Rule):
    """
    Soft-penalty for fairness: minimize L1 deviation from equal total hours.

    Config used:
      ENABLE_FAIRNESS (bool)
      COVER, HOURS, DAYS, N
      FAIRNESS_WEIGHT_PER_HOUR (int)
    """

    order = 90
    name = "Fairness"

    def __init__(self, model):
        super().__init__(model)
        self.enabled = model.cfg.ENABLE_FAIRNESS  # toggle via config

    def contribute_objective(self):
        if not self.enabled:
            return []
        C, M = self.model.cfg, self.model.m
        terms = []
        # Equal target = total required hours / headcount
        target = C.COVER * C.HOURS * C.DAYS / C.N
        t_floor, t_ceil = int(np.floor(target)), int(np.ceil(target))

        for e in range(C.N):
            # T_e = total hours assigned to employee e
            T_e = M.NewIntVar(0, C.DAYS * C.HOURS, f"T_e{e}")
            M.Add(
                T_e
                == sum(
                    self.model.x[(e, d, h)]
                    for d in range(C.DAYS)
                    for h in range(C.HOURS)
                )
            )
            # L1 deviation |T_e - target| via two half-planes
            dev = M.NewIntVar(0, C.DAYS * C.HOURS, f"dev_e{e}")
            M.Add(dev >= T_e - t_floor)
            M.Add(dev >= t_ceil - T_e)

            terms.append(C.FAIRNESS_WEIGHT_PER_HOUR * dev)

        return terms
