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
    localparam       MEM_SIZE   = 32'h0100_0000;
    localparam [4:0] ADDR_WIDTH = $$clog2(MEM_SIZE);
    localparam       BASE_ADDR  = 32'h8000_0000;

    wire [31:0]  mport__addr;
    wire [31:0]  mport__dat_w;
    wire [3:0]   mport__sel;
    wire         mport__we;
    // wire [2:0]   mport__cti;
    // wire [1:0]   mport__bte;
    wire         mport__cyc;
    wire         mport__stb;
    wire [31:0]  mport__dat_r;
    wire         mport__ack;
    wire         mport__err;

    wire [31:0]  slave_addr;
    wire [31:0]  slave_dat_w;
    wire [3:0]   slave_sel;
    wire         slave_we;
    wire [2:0]   slave_cti;
    wire [1:0]   slave_bte;
    wire         slave0_cyc;
    wire         slave0_stb;
    wire [31:0]  slave0_dat_r;
    wire         slave0_ack;

    wire         slave1_cyc;
    wire         slave1_stb;
    wire [31:0]  slave1_dat_r;
    wire         slave1_ack;
    wire         slave1_err;
    wire         external_interrupt;
    wire         timer_interrupt;
    wire         software_interrupt;

    wire         unused;

    altair_core cpu (// Outputs
                     .mport__adr         (mport__addr[31:0]),
                     .mport__dat_w       (mport__dat_w),
                     .mport__sel         (mport__sel),
                     .mport__cyc         (mport__cyc),
                     .mport__stb         (mport__stb),
                     .mport__we          (mport__we),
                     // Inputs
                     .clk                (clk),
                     .rst                (rst),
                     .mport__dat_r       (mport__dat_r[31:0]),
                     .mport__ack         (mport__ack),
                     .mport__err         (mport__err),
                     .external_interrupt (external_interrupt),
                     .timer_interrupt    (timer_interrupt),
                     .software_interrupt (software_interrupt)
                     );

    mux_switch #(// Parameters
                 .NSLAVES    (2),
                 //            1              0
                 .BASE_ADDR  ({32'h1000_0000, BASE_ADDR}),
                 .ADDR_WIDTH ({5'd8,          ADDR_WIDTH})
                 ) bus0 (// Outputs
                         .master_rdata   (mport__dat_r[31:0]),
                         .master_ack     (mport__ack),
                         .master_err     (mport__err),
                         .slave_addr     (slave_addr[31:0]),
                         .slave_wdata    (slave_dat_w[31:0]),
                         .slave_sel      (slave_sel[3:0]),
                         .slave_we       (slave_we),
                         .slave_cyc      ({slave1_cyc, slave0_cyc}),
                         .slave_stb      ({slave1_stb, slave0_stb}),
                         .slave_cti      (slave_cti),
                         .slave_bte      (slave_bte),
                         // Inputs
                         .master_addr    (mport__addr[31:0]),
                         .master_wdata   (mport__dat_w[31:0]),
                         .master_sel     (mport__sel[3:0]),
                         .master_we      (mport__we),
                         .master_cyc     (mport__cyc),
                         .master_stb     (mport__stb),
                         .master_cti     (0),
                         .master_bte     (0),
                         .slave_rdata    ({slave1_dat_r, slave0_dat_r}),
                         .slave_ack      ({slave1_ack,   slave0_ack}),
                         .slave_err      ({slave1_err,   1'b0})
                         );

    // slave 0: @BASE_ADDR
    ram #(// Parameters
          .ADDR_WIDTH (ADDR_WIDTH),
          .BASE_ADDR  (BASE_ADDR)
          ) memory (/*AUTOINST*/
                    // Outputs
                    .dwbs_dat_r        (slave0_dat_r[31:0]),
                    .dwbs_ack          (slave0_ack),
                    // Inputs
                    .clk               (clk),
                    .rst               (rst),
                    .dwbs_addr         (slave_addr[31:0]),
                    .dwbs_dat_w        (slave_dat_w[31:0]),
                    .dwbs_sel          (slave_sel[3:0]),
                    .dwbs_cyc          (slave0_cyc),
                    .dwbs_stb          (slave0_stb),
                    .dwbs_cti          (slave_cti),
                    .dwbs_bte          (slave_bte),
                    .dwbs_we           (slave_we)
                    );

    // slave 1: @0x1000_0000
    interrupt int_helper(
                         .clk                (clk),
                         .rst                (rst),
                         .int_addr           (slave_addr),
                         .int_dat_w          (slave_dat_w),
                         .int_sel            (slave_sel),
                         .int_cyc            (slave1_cyc),
                         .int_stb            (slave1_stb),
                         .int_cti            (slave_cti),
                         .int_bte            (slave_bte),
                         .int_we             (slave_we),
                         .int_dat_r          (slave1_dat_r),
                         .int_ack            (slave1_ack),
                         .int_err            (slave1_err),
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
