"""Orders out to the partner feed, one dict a row. An order is {"id": int, "cents": int}."""


def export_row(order):
    return {"id": order["id"], "amt": order["cents"]}


def export(orders):
    return [export_row(o) for o in orders]
