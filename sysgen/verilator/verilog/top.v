// -----------------------------------------------------------------------------
// Copyright (C) 2019 Angel Terrones <angelterrones@gmail.com>
// -----------------------------------------------------------------------------

`default_nettype none

module top (
    input wire         clk,
    input wire         rst,
    output wire [31:0]  io__addr,
    output wire [31:0] io__dat_w,
    output wire [3:0]  io__sel,
    output wire        io__we,
    output wire        io__cyc,
    output wire        io__stb,
    input wire [31:0]  io__dat_r,
    input wire         io__ack,
    input wire         io__err,
    input wire [32:0]  interrupts
    );
    //--------------------------------------------------------------------------
    localparam       BASE_ADDR  = $RAM_ADDR;
    localparam [4:0] ADDR_WIDTH = $RAM_ADDR_WIDTH;

    wire [ADDR_WIDTH - 1:0]  mport__addr;
    wire [31:0]              mport__dat_w;
    wire [3:0]               mport__sel;
    wire                     mport__we;
    wire                     mport__cyc;
    wire                     mport__stb;
    wire [31:0]              mport__dat_r;
    wire                     mport__ack;
    wire                     mport__err;

    wire         unused;

    $CORENAME cpu (// Outputs
                     .mport__adr         (mport__addr),
                     .mport__dat_w       (mport__dat_w),
                     .mport__sel         (mport__sel),
                     .mport__cyc         (mport__cyc),
                     .mport__stb         (mport__stb),
                     .mport__we          (mport__we),
                     .interrupts         (interrupts),
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
                     .io__err            (io__err)
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
    //--------------------------------------------------------------------------
endmodule

// Local Variables:
// verilog-library-directories: ("." "../../../rtl")
// flycheck-verilator-include-path: ("." "../../../rtl")
// End:
