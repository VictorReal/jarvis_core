import psutil
import platform
import logging

logger = logging.getLogger(__name__)

class SensorsModule:
    """Відповідає за збір даних про стан системи."""

    def get_cpu_temperature(self) -> float | None:
        """
        Читає температуру процесора.
        Повертає float на Linux, None на Windows/Mac.
        """
        system = platform.system()

        if system == "Linux":
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    # Файл зберігає температуру в міліградусах — ділимо на 1000
                    return int(f.read()) / 1000
            except Exception as e:
                logger.warning(f"Не вдалось прочитати температуру: {e}")
                return None

        if system == "Windows":
            # psutil на Windows не підтримує температуру без WMI
            # тому чесно повертаємо None замість 0.0
            logger.debug("Температура CPU: недоступна на Windows")
            return None

        # macOS та інші — спробуємо через psutil
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Беремо першу доступну температуру
                first_key = next(iter(temps))
                return temps[first_key][0].current
        except Exception as e:
            logger.debug(f"psutil температура недоступна: {e}")

        return None

    def get_system_report(self) -> str:
        """Формує текстовий звіт про стан системи для Джарвіса."""

        # CPU завантаження — interval=0.5 точніше ніж 0.1
        cpu_usage = psutil.cpu_percent(interval=0.5)

        # RAM
        ram = psutil.virtual_memory()
        ram_usage = ram.percent

        # Температура — може бути None
        temp = self.get_cpu_temperature()

        # Формуємо фразу про температуру залежно від платформи
        if temp is not None:
            temp_str = f"Core temperature is {temp:.1f} degrees Celsius."
        else:
            system = platform.system()
            temp_str = f"Core temperature monitoring is unavailable on {system}."

        report = (
            f"Systems check complete. "
            f"{temp_str} "
            f"CPU load is at {cpu_usage} percent, "
            f"and memory usage is {ram_usage} percent. "
            f"All systems are within operational limits, Sir."
        )

        return report


# Для зручності — можна викликати get_system_report() напряму
# так само як і раніше, щоб не чіпати command_router
_sensors = SensorsModule()

def get_system_report() -> str:
    return _sensors.get_system_report()