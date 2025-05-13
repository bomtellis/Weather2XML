import asyncio, json
from open_meteo import OpenMeteo
from open_meteo.models import DailyParameters, HourlyParameters

# Longitude, Latitude
latitude = 53.122
longitude = -2.4803


def remove_empty_elements(d):
    """recursively remove empty lists, empty dicts, or None elements from a dictionary"""

    def empty(x):
        return x is None or x == {} or x == []

    if not isinstance(d, (dict, list)):
        return d
    elif isinstance(d, list):
        return [v for v in (remove_empty_elements(v) for v in d) if not empty(v)]
    else:
        return {
            k: v
            for k, v in ((k, remove_empty_elements(v)) for k, v in d.items())
            if not empty(v)
        }


async def main():
    async with OpenMeteo() as om:
        forecast = await om.forecast(
            latitude=latitude,
            longitude=longitude,
            current_weather=False,
            timezone="Europe/London",
            daily=[DailyParameters.SUNRISE, DailyParameters.SUNSET],
            hourly=[HourlyParameters.TEMPERATURE_2M],
        )

        rawdata = forecast.to_json()
        data = json.loads(rawdata)
        data = remove_empty_elements(data)
        print(data)

        # Write to file - create new file
        try:
            with open("weather_data.json", "x") as f:
                f.write(json.dumps(data))
        except FileExistsError:
            with open("weather_data.json", "w") as f:
                f.write(json.dumps(data))
        except Exception as e:
            print("error", e)


if __name__ == "__main__":
    asyncio.run(main())
