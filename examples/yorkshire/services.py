from examples.yorkshire.domain import Yorkshire


class VetService:
    def checkup(self, dog: Yorkshire) -> dict[str, object]:
        base_weight = {"teacup": 1.5, "mini": 2.5, "standard": 3.5}
        return {
            "healthy": True,
            "weight": base_weight[dog.size.value],
            "age_months": dog.age,
            "needs_vaccination": dog.age < 24,
        }

    def vaccinate(self, dog: Yorkshire) -> bool:
        return dog.age >= 8


class GroomingService:
    async def groom(self, dog: Yorkshire) -> float:
        base_price = {"teacup": 25.0, "mini": 35.0, "standard": 45.0}
        coat_multiplier = {"long": 1.5, "short": 1.0, "silky": 1.3}
        price = base_price[dog.size.value]
        if hasattr(dog, "coat"):
            price *= coat_multiplier.get(dog.coat.value, 1.0)
        return price

    async def schedule_appointment(self, dog: Yorkshire, date: str) -> str:
        return f"APT-{dog.name[:3].upper()}-{date.replace('-', '')}"
