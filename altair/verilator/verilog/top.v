// -----------------------------------------------------------------------------
// Copyright (C) 2019 Angel Terrones <angelterrones@gmail.com>
// -----------------------------------------------------------------------------

`default_nettype none
`timescale 1 ns / 1 ps

module top (
    input wire clk,
    input wire rst
    );
    //--------------------------------------------------------------------------
    localparam       BASE_ADDR  = 32'h8000_0000;
    localparam [4:0] ADDR_WIDTH = 20;

    wire [ADDR_WIDTH - 1:0]  mport__addr;
    wire [31:0]              mport__dat_w;
    wire [3:0]               mport__sel;
    wire                     mport__we;
    wire                     mport__cyc;
    wire                     mport__stb;
    wire [31:0]              mport__dat_r;
    wire                     mport__ack;
    wire                     mport__err;

    wire [5:0]  io__addr;
    wire [31:0] io__dat_w;
    wire [3:0]  io__sel;
    wire        io__we;
    wire        io__cyc;
    wire        io__stb;
    wire [31:0] io__dat_r;
    wire        io__ack;
    wire        io__err;

    wire  external_interrupt;
    wire  timer_interrupt;
    wire  software_interrupt;

    wire         unused;

    altair_core cpu (// Outputs
                     .mport__adr         (mport__addr),
                     .mport__dat_w       (mport__dat_w),
                     .mport__sel         (mport__sel),
                     .mport__cyc         (mport__cyc),
                     .mport__stb         (mport__stb),
                     .mport__we          (mport__we),
                     .io__adr            (io__addr),
                     .io__dat_w          (io__dat_w),
                     .io__sel            (io__sel),
                     .io__cyc            (io__cyc),
                     .io__stb            (io__stb),
                     .io__we             (io__we),
                     // Inputs
                     .clk                (clk),
                     .rst                (rst),
                     .mport__dat_r       (mport__dat_r),
                     .mport__ack         (mport__ack),
                     .mport__err         (0),
                     .io__dat_r          (io__dat_r),
                     .io__ack            (io__ack),
                     .io__err            (io__err),
                     .external_interrupt (external_interrupt),
                     .timer_interrupt    (timer_interrupt),
                     .software_interrupt (software_interrupt)
                     );

    // slave 0: @BASE_ADDR
    ram #(// Parameters
          .ADDR_WIDTH (ADDR_WIDTH),
          .BASE_ADDR  (BASE_ADDR)
          ) memory (/*AUTOINST*/
                    // Outputs
                    .dwbs_dat_r        (mport__dat_r),
                    .dwbs_ack          (mport__ack),
                    // Inputs
                    .clk               (clk),
                    .rst               (rst),
                    .dwbs_addr         (mport__addr),
                    .dwbs_dat_w        (mport__dat_w),
                    .dwbs_sel          (mport__sel),
                    .dwbs_cyc          (mport__cyc),
                    .dwbs_stb          (mport__stb),
                    .dwbs_cti          (0),
                    .dwbs_bte          (0),
                    .dwbs_we           (mport__we)
                    );

    // slave 1: @0x1000_0000
    interrupt int_helper(
                         .clk                (clk),
                         .rst                (rst),
                         .int_addr           (io__addr),
                         .int_dat_w          (io__dat_w),
                         .int_sel            (io__sel),
                         .int_cyc            (io__cyc),
                         .int_stb            (io__stb),
                         .int_cti            (0),
                         .int_bte            (0),
                         .int_we             (io__we),
                         .int_dat_r          (io__dat_r),
                         .int_ack            (io__ack),
                         .int_err            (io__err),
                         .external_interrupt (external_interrupt),
                         .timer_interrupt    (timer_interrupt),
                         .software_interrupt (software_interrupt)
                         );
    //--------------------------------------------------------------------------
endmodule

// Local Variables:
// verilog-library-directories: ("." "../../../rtl")
// flycheck-verilator-include-path: ("." "../../../rtl")
// End:
