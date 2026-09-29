// SPDX-License-Identifier: GPL-2.0-only
/*
 * Bring-up aid, not for shipping: power a camera sensor described in DT
 * (supplies, "xvclk" at clock-frequency, reset-gpios) and print the chip ID
 * register(s) listed in "a52q,id-regs" (16-bit address, 16-bit read).
 */
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regulator/consumer.h>

static const char * const supplies[] = { "vio", "vana", "vdig", "vaf", "vcustom" };

static bool addr8;

static int rd16(struct i2c_client *c, u16 reg, u16 *val)
{
	u8 a[2] = { reg >> 8, reg & 0xff }, v[2];
	struct i2c_msg m[2] = {
		{ .addr = c->addr, .len = 2, .buf = a },
		{ .addr = c->addr, .flags = I2C_M_RD, .len = 2, .buf = v },
	};
	int ret;

	if (addr8) {		/* 8-bit register address (GalaxyCore) */
		a[0] = reg & 0xff;
		m[0].len = 1;
	}
	ret = i2c_transfer(c->adapter, m, 2);

	*val = (v[0] << 8) | v[1];
	return ret == 2 ? 0 : (ret < 0 ? ret : -EIO);
}

static int cam_probe(struct i2c_client *c)
{
	struct device *dev = &c->dev;
	struct regulator *r;
	struct gpio_desc *rst;
	struct clk *clk;
	u32 freq = 24000000, regs[4];
	int i, n, ret;

	for (i = 0; i < ARRAY_SIZE(supplies); i++) {
		r = devm_regulator_get_optional(dev, supplies[i]);
		if (IS_ERR(r)) {
			if (PTR_ERR(r) == -EPROBE_DEFER)
				return -EPROBE_DEFER;
			continue;
		}
		ret = regulator_enable(r);
		dev_info(dev, "%s on: %d (%d uV)\n", supplies[i], ret, regulator_get_voltage(r));
	}
	of_property_read_u32(dev->of_node, "clock-frequency", &freq);
	clk = devm_clk_get_optional(dev, "xvclk");
	if (IS_ERR(clk))
		return PTR_ERR(clk);
	clk_set_rate(clk, freq);
	ret = clk_prepare_enable(clk);
	dev_info(dev, "mclk %lu: %d\n", clk_get_rate(clk), ret);

	rst = devm_gpiod_get_optional(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(rst))
		return PTR_ERR(rst);
	usleep_range(2000, 3000);
	gpiod_set_value_cansleep(rst, 0);
	msleep(20);

	addr8 = of_property_read_bool(dev->of_node, "a52q,addr8");
	n = of_property_read_variable_u32_array(dev->of_node, "a52q,id-regs", regs, 1, 4);
	for (i = 0; i < n; i++) {
		u16 v = 0;

		ret = rd16(c, regs[i], &v);
		dev_info(dev, "addr 0x%02x reg 0x%04x = 0x%04x (ret %d)\n", c->addr, regs[i], v, ret);
	}
	return 0;
}

static const struct of_device_id cam_probe_of[] = {
	{ .compatible = "a52q,cam-probe" },
	{}
};
MODULE_DEVICE_TABLE(of, cam_probe_of);

static struct i2c_driver cam_probe_driver = {
	.driver = { .name = "a52q-cam-probe", .of_match_table = cam_probe_of },
	.probe = cam_probe,
};
module_i2c_driver(cam_probe_driver);
MODULE_DESCRIPTION("a52q camera bring-up probe");
MODULE_LICENSE("GPL");
