/*
 * Copyright 2018 Maciej Grela <enki@fsck.pl>
 * SPDX-License-Identifier: WTFPL
 *
 * Capture traffic and send ERSPAN frames.
 * Needs to be linked with libpcap.
 */

#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <linux/if_packet.h>
#include <net/if.h>
#include <net/ethernet.h> /* the L2 protocols */
#include <netinet/if_ether.h>

#include <pcap.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <errno.h>
#include <arpa/inet.h>

/* Credits: http://stackoverflow.com/questions/7775991/how-to-get-hexdump-of-a-structure-data  */
void hexDump (void *addr, int len) {
    int i;
    unsigned char buff[17];
    unsigned char *pc = (unsigned char*)addr;

    if (len == 0) {
        printf("  ZERO LENGTH\n");
        return;
    }
    if (len < 0) {
        printf("  NEGATIVE LENGTH: %i\n",len);
        return;
    }

    // Process every byte in the data.
    for (i = 0; i < len; i++) {
        // Multiple of 16 means new line (with line offset).

        if ((i % 16) == 0) {
            // Just don't print ASCII for the zeroth line.
            if (i != 0)
                printf ("  %s\n", buff);

            // Output the offset.
            printf ("  %04x ", i);
        }

        // Now the hex code for the specific character.
        printf (" %02x", pc[i]);

        // And store a printable ASCII character for later.
        if ((pc[i] < 0x20) || (pc[i] > 0x7e))
            buff[i % 16] = '.';
        else
            buff[i % 16] = pc[i];
        buff[(i % 16) + 1] = '\0';
    }

    // Pad out last line if not exactly 16 characters.
    while ((i % 16) != 0) {
        printf ("   ");
        i++;
    }

    // And print the final ASCII bit.
    printf ("  %s\n", buff);
}


#define ETHERTYPE_ERSPAN 0x88be
struct erspan_hdr {
#define ERSPAN_VER2 (1U << 12)
  u_int16_t ver_vlan; /* Version and VLAN ID */
#define ERSPAN_TRUNCATED (1U << 10)
  u_int16_t flags_spanid; /* Flags and SPAN ID */
  u_int32_t unknown;
} __attribute__((packed));

int main(int argc, char **argv) {

  u_int16_t span_id = 100;
  u_int16_t vlan = 1;

  struct erspan_hdr ehdr = {0};
  ehdr.ver_vlan = htons(vlan | ERSPAN_VER2);
  ehdr.flags_spanid = htons(span_id);

  const char *if_name = argv[1];
  const char *capture_if = argv[2];

  int s = socket(AF_PACKET, SOCK_DGRAM, htons(ETH_P_ALL));

  struct ifreq ifr;
  size_t if_name_len=strlen(if_name);
  if (if_name_len<sizeof(ifr.ifr_name)) {
    memcpy(ifr.ifr_name,if_name,if_name_len);
    ifr.ifr_name[if_name_len]=0;
  } else {
    fprintf(stderr, "interface name is too long");
    exit(EXIT_FAILURE);
  }
  if (ioctl(s,SIOCGIFINDEX,&ifr)==-1) {
    fprintf(stderr, "%s",strerror(errno));
    exit(EXIT_FAILURE);
  }
  int ifindex=ifr.ifr_ifindex;

  struct sockaddr_ll addr = {0};
  addr.sll_family=AF_PACKET;
  addr.sll_ifindex=ifindex;
  addr.sll_protocol=htons(ETHERTYPE_ERSPAN);

  struct iovec pkt_iovs[] = {
    {
      .iov_base = (void *)&ehdr,
      .iov_len = sizeof(ehdr)
    },
    {
      .iov_base = (void *)NULL,
      .iov_len = 0
    }
  };

  struct msghdr msg = {0};
  msg.msg_name = &addr;
  msg.msg_namelen = sizeof(addr);
  msg.msg_iov = &pkt_iovs;
  msg.msg_iovlen = 2;

  printf("Capturing on interface '%s'\n", capture_if);

#define SNAPLEN 4096

  char errbuf[PCAP_ERRBUF_SIZE];	/* Error string */
  pcap_t *capture = pcap_open_live(capture_if, SNAPLEN, 1, 1000, errbuf);

  struct pcap_pkthdr header;	/* The header that pcap gives us */
  const u_char *packet;		/* The actual packet */
  while (1) {
		packet = pcap_next(capture, &header);

		printf("Jacked a packet with length of [%d]\n", header.len);

		pkt_iovs[1].iov_base = packet;
    pkt_iovs[1].iov_len = header.len;

    if (sendmsg(s,&msg,0)==-1) {
      fprintf(stderr, "%s",strerror(errno));
      exit(EXIT_FAILURE);
    }

  }

  return 0;
}
