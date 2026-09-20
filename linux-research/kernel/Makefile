obj-m += avid_native_dma_probe.o
obj-m += avid_native_alsa.o
obj-m += avid_native_desktop.o
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean

obj-m += avid_native_capture.o

obj-m += avid_native_duplex.o
