from decimal import ROUND_CEILING, ROUND_FLOOR
from decimal import Decimal as D

q = D("0.00000001")


def c(x):
    return x.quantize(q, ROUND_CEILING)


def br(r, lim):
    return r * lim + c(r * lim * D("0.001")) + (r / D("0.00001")) * q


print(br(D("0.0005"), D("99000")), br(D("0.0003"), D("99000")), br(D("0.0003"), D("100050")))
print(c(D("0.00001") * D("100000.01") * D("0.0005")))
print(D(100) - D("19.8") - c(D("19.8") * D("0.0005")))
print(sum(c(x * D("0.001")) for x in (D("20"), D("20.002"), D("10.002"))))
print((D("100000.03") * D("0.9995")).quantize(D("0.01"), ROUND_FLOOR), (D("100000.03") * D("1.0005")).quantize(D("0.01"), ROUND_CEILING))
print((D("100040") * D("0.9995")).quantize(D("0.01"), ROUND_FLOOR), (D(101000) * D("0.9995")).quantize(D("0.01"), ROUND_FLOOR))
print((D(20) / (D(100000) * D("1.001"))).quantize(D("0.00001"), ROUND_FLOOR), (D(100) / (D(100000) * D("1.001"))).quantize(D("0.00001"), ROUND_FLOOR))
