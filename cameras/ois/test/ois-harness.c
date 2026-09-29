// SPDX-License-Identifier: GPL-2.0
/*
 * TEST ONLY: instantiate the a52q OIS MCU without a DT change, so the
 * samsung-ois-mcu driver can be tested on the running kernel.
 *  - i2c-gpio bus 10 on TLMM gpio86 (SDA) / gpio87 (SCL) (QUP i2c10 pins)
 *  - i2c client "a52q-ois-mcu" @0x62 with reset (gpio32) / boot0 (gpio43)
 *  - vdd/vio supplies aliased to the main sensor's vaf/vcustom supplies
 *  - runtime-PM device link main sensor (20-002d) -> OIS, as the DT property
 *    "samsung,camera-sensor" does in the real driver
 * Load this BEFORE samsung-ois-mcu.ko, unload the driver first.
 */
#include <linux/device.h>
#include <linux/gpio/machine.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/platform_data/i2c-gpio.h>
#include <linux/platform_device.h>
#include <linux/regulator/consumer.h>

#define TLMM "3500000.pinctrl"

static struct gpiod_lookup_table bus_gpios = {
	.dev_id = "i2c-gpio.10",
	.table = {
		GPIO_LOOKUP(TLMM, 86, "sda", GPIO_ACTIVE_HIGH),
		GPIO_LOOKUP(TLMM, 87, "scl", GPIO_ACTIVE_HIGH),
		{ }
	},
};

static struct gpiod_lookup_table ois_gpios = {
	.dev_id = "10-0062",
	.table = {
		GPIO_LOOKUP(TLMM, 32, "reset", GPIO_ACTIVE_LOW),
		GPIO_LOOKUP(TLMM, 43, "boot0", GPIO_ACTIVE_HIGH),
		{ }
	},
};

static struct i2c_gpio_platform_data bus_pdata = {
	.udelay = 5,		/* 100 kHz */
	.timeout = HZ,		/* the MCU stretches SCL */
};

static struct platform_device *bus;
static struct i2c_client *ois;
static struct device *sensor;
static struct device_link *link;

static int __init harness_init(void)
{
	struct i2c_board_info info = { I2C_BOARD_INFO("a52q-ois-mcu", 0x62) };
	struct i2c_adapter *adap;
	int ret;

	sensor = bus_find_device_by_name(&i2c_bus_type, NULL, "20-002d");
	if (!sensor)
		return -ENODEV;

	gpiod_add_lookup_table(&bus_gpios);
	gpiod_add_lookup_table(&ois_gpios);
	bus = platform_device_register_data(NULL, "i2c-gpio", 10, &bus_pdata,
					    sizeof(bus_pdata));
	ret = PTR_ERR_OR_ZERO(bus);
	if (ret)
		goto err_lookup;

	adap = i2c_get_adapter(10);
	if (!adap) {
		ret = -EPROBE_DEFER;	/* i2c-gpio not loaded? */
		goto err_bus;
	}
	ois = i2c_new_client_device(adap, &info);
	i2c_put_adapter(adap);
	ret = PTR_ERR_OR_ZERO(ois);
	if (ret)
		goto err_bus;

	ret = regulator_register_supply_alias(&ois->dev, "vdd", sensor, "vaf");
	if (ret)
		goto err_client;
	ret = regulator_register_supply_alias(&ois->dev, "vio", sensor, "vcustom");
	if (ret)
		goto err_alias;

	link = device_link_add(sensor, &ois->dev,
			       DL_FLAG_STATELESS | DL_FLAG_PM_RUNTIME);
	if (!link) {
		ret = -EINVAL;
		goto err_alias2;
	}
	return 0;

err_alias2:
	regulator_unregister_supply_alias(&ois->dev, "vio");
err_alias:
	regulator_unregister_supply_alias(&ois->dev, "vdd");
err_client:
	i2c_unregister_device(ois);
err_bus:
	platform_device_unregister(bus);
err_lookup:
	gpiod_remove_lookup_table(&ois_gpios);
	gpiod_remove_lookup_table(&bus_gpios);
	put_device(sensor);
	return ret;
}

static void __exit harness_exit(void)
{
	device_link_del(link);
	regulator_unregister_supply_alias(&ois->dev, "vio");
	regulator_unregister_supply_alias(&ois->dev, "vdd");
	i2c_unregister_device(ois);
	platform_device_unregister(bus);
	gpiod_remove_lookup_table(&ois_gpios);
	gpiod_remove_lookup_table(&bus_gpios);
	put_device(sensor);
}

module_init(harness_init);
module_exit(harness_exit);
MODULE_DESCRIPTION("a52q OIS MCU test harness (no DT change)");
MODULE_LICENSE("GPL");
